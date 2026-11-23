import ast
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    header_end,
    walk_outside,
)

_TYPE_PARAMS = (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)
_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)

type _Nested = (
    ast.FunctionDef
    | ast.AsyncFunctionDef
    | ast.Lambda
    | ast.ClassDef
    | ast.ListComp
    | ast.SetComp
    | ast.DictComp
    | ast.GeneratorExp
)
type _Scope = ast.Module | _Nested


class NameKind(Enum):
    """What a declared name refers to."""

    MODULE_VAR = auto()  # bound at module level
    CLASS_VAR = auto()  # bound in a class body
    LOCAL_VAR = auto()  # a parameter, or bound in a function, lambda or comprehension
    TYPE_PARAM = auto()
    FUNC = auto()  # a def other than a TEST_FUNC
    TEST_FUNC = auto()  # a def named test_*
    CLASS = auto()


@dataclass(frozen=True)
class DeclaredName:
    """A name's first binding in a scope."""

    text: str
    line: int
    last_line: int  # where a nolint may still sit, unless the name is a def or class
    kind: NameKind
    node: ast.AST


def declared_names(file: CheckInput) -> list[DeclaredName]:
    """Return the first binding of each name in every scope of file, in line order."""
    scopes: list[_Scope] = [file.tree]
    scopes += [node for node in ast.walk(file.tree) if isinstance(node, _SCOPES)]
    names = [name for scope in scopes for name in _first_bindings(file, scope)]
    return sorted(names, key=lambda name: name.line)


def _first_bindings(file: CheckInput, scope: _Scope) -> list[DeclaredName]:
    var_kind = _var_kind(scope)
    nodes = list(_scope_nodes(_own_parts(scope)))
    declared = {
        name
        for node in nodes
        if isinstance(node, ast.Global | ast.Nonlocal)
        for name in node.names
    }
    found = [_binding(file, node, var_kind) for node in nodes]
    bindings = [name for name in found if name is not None]
    firsts: dict[ast.AST | str, DeclaredName] = {}
    for name in sorted(bindings, key=lambda name: name.line):
        key = _scope_key(name, declared)
        if key is not None:
            firsts.setdefault(key, name)
    return list(firsts.values())


def _var_kind(scope: _Scope) -> NameKind:
    if isinstance(scope, ast.Module):
        return NameKind.MODULE_VAR
    if isinstance(scope, ast.ClassDef):
        return NameKind.CLASS_VAR
    return NameKind.LOCAL_VAR


def _scope_key(name: DeclaredName, declared: set[str]) -> ast.AST | str | None:
    """Return name's key in its scope, or None if global or nonlocal moves it.

    Each type parameter has an annotation scope of its own, which the body's
    global and nonlocal statements don't reach.
    """
    if isinstance(name.node, _TYPE_PARAMS):
        return name.node
    return None if name.text in declared else name.text


def _own_parts(scope: _Scope) -> list[ast.AST]:
    """Return the parts of scope whose names bind in it.

    Only a comprehension's loop targets are its own; a walrus in it binds in
    the scope around it.
    """
    if isinstance(scope, ast.Module):
        return list(scope.body)
    if isinstance(scope, ast.ClassDef):
        return [*scope.type_params, *scope.body]
    if isinstance(scope, ast.Lambda):
        return [*_params(scope.args), scope.body]
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        return [*scope.type_params, *_params(scope.args), *scope.body]
    return [gen.target for gen in scope.generators]


def _scope_nodes(nodes: list[ast.AST]) -> Iterator[ast.AST]:
    """Yield nodes and the nodes under them that bind in the scope holding them.

    A nested scope's name binds in the scope around it, and so do names in its
    defaults, annotations, decorators and bases and a walrus in a comprehension.
    A parameter is entered only through its outer parts.
    """
    for node in walk_outside(nodes, (*_SCOPES, ast.arg)):
        yield node
        if isinstance(node, _SCOPES):
            yield from _scope_nodes(_outer_parts(node))


def _outer_parts(scope: _Nested) -> list[ast.AST]:
    if isinstance(scope, ast.ClassDef):
        return [*scope.decorator_list, *scope.bases, *scope.keywords]
    if isinstance(scope, ast.Lambda):
        return _defaults(scope.args)
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        params = _params(scope.args)
        annotations = [param.annotation for param in params if param.annotation]
        returns = [scope.returns] if scope.returns else []
        return [*scope.decorator_list, *_defaults(scope.args), *annotations, *returns]
    if isinstance(scope, ast.DictComp):
        elements = [scope.key, scope.value]
    else:
        elements = [scope.elt]
    tests = [part for gen in scope.generators for part in (gen.iter, *gen.ifs)]
    return [*elements, *tests]


def _params(args: ast.arguments) -> list[ast.arg]:
    params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
    return [param for param in params if param is not None]


def _defaults(args: ast.arguments) -> list[ast.AST]:
    return [default for default in (*args.defaults, *args.kw_defaults) if default]


def _binding(
    file: CheckInput, node: ast.AST, var_kind: NameKind
) -> DeclaredName | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        is_test = node.name.startswith("test_")
        func_kind = NameKind.TEST_FUNC if is_test else NameKind.FUNC
        return DeclaredName(node.name, node.lineno, node.lineno, func_kind, node)
    if isinstance(node, ast.ClassDef):
        return DeclaredName(node.name, node.lineno, node.lineno, NameKind.CLASS, node)
    if isinstance(node, _TYPE_PARAMS):
        return DeclaredName(
            node.name, node.lineno, node.lineno, NameKind.TYPE_PARAM, node
        )
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return DeclaredName(node.id, node.lineno, node.lineno, var_kind, node)
    if isinstance(node, ast.arg):
        return DeclaredName(node.arg, node.lineno, node.lineno, var_kind, node)
    return _clause_binding(file, node, var_kind)


def _clause_binding(
    file: CheckInput, node: ast.AST, var_kind: NameKind
) -> DeclaredName | None:
    """Return the name an except alias or match pattern binds, if any.

    An except alias has no position of its own; it ends the clause header. A
    capture name ends its pattern, which can span lines. A mapping rest has no
    position of its own either, so a nolint may sit on any line of the pattern.
    """
    if isinstance(node, ast.ExceptHandler) and node.name:
        line = header_end(file, node)
        return DeclaredName(node.name, line, line, var_kind, node)
    if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
        line = node.end_lineno or node.lineno
        return DeclaredName(node.name, line, line, var_kind, node)
    if isinstance(node, ast.MatchMapping) and node.rest:
        last_line = node.end_lineno or node.lineno
        return DeclaredName(node.rest, node.lineno, last_line, var_kind, node)
    return None
