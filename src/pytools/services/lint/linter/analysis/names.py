import ast
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    header_end,
    is_test_func,
    walk_outside,
)

_TYPE_PARAMS: Final = (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)
SCOPES: Final = (
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
    scopes += [node for node in ast.walk(file.tree) if isinstance(node, SCOPES)]
    names = [name for scope in scopes for name in first_bindings(file, scope)]
    return sorted(names, key=lambda name: name.line)


def first_bindings(file: CheckInput, scope: _Scope) -> list[DeclaredName]:
    """Return the first binding of each name that binds in scope itself."""
    var_kind = _var_kind(scope)
    nodes = list(_scope_nodes(own_parts(scope)))
    declared = {
        name
        for node in nodes
        if isinstance(node, ast.Global | ast.Nonlocal)
        for name in node.names
    }
    found = [binding(file, node, var_kind) for node in nodes]
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


def _scope_nodes(nodes: list[ast.AST]) -> Iterator[ast.AST]:
    """Yield nodes and the nodes under them that bind in the scope holding them."""
    for node in walk_outside(nodes, (*SCOPES, ast.arg)):
        yield node
        if isinstance(node, SCOPES):
            yield from _scope_nodes(outer_parts(node))


def outer_parts(scope: _Nested) -> list[ast.AST]:
    """Return the parts of scope that run in the scope around it."""
    if isinstance(scope, ast.ClassDef):
        return [*scope.decorator_list, *scope.bases, *scope.keywords]
    if isinstance(scope, ast.Lambda):
        return param_defaults(scope.args)
    if isinstance(scope, DEFS):
        params = _params(scope.args)
        annotations = [param.annotation for param in params if param.annotation]
        returns = [scope.returns] if scope.returns else []
        defaults = param_defaults(scope.args)
        return [*scope.decorator_list, *defaults, *annotations, *returns]
    if isinstance(scope, ast.DictComp):
        elements = [scope.key, scope.value]
    else:
        elements = [scope.elt]
    tests = [part for gen in scope.generators for part in (gen.iter, *gen.ifs)]
    return [*elements, *tests]


def param_defaults(args: ast.arguments) -> list[ast.AST]:
    """Return the default values of args."""
    return [default for default in (*args.defaults, *args.kw_defaults) if default]


# A walrus in a comprehension binds in the scope around it.
def own_parts(scope: _Scope) -> list[ast.AST]:
    """Return the parts of scope whose names bind in it."""
    if isinstance(scope, ast.Module):
        return list(scope.body)
    if isinstance(scope, ast.ClassDef):
        return [*scope.type_params, *scope.body]
    if isinstance(scope, ast.Lambda):
        return [*_params(scope.args), scope.body]
    if isinstance(scope, DEFS):
        return [*scope.type_params, *_params(scope.args), *scope.body]
    return [gen.target for gen in scope.generators]


def _params(args: ast.arguments) -> list[ast.arg]:
    params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
    return [param for param in params if param is not None]


def binding(file: CheckInput, node: ast.AST, var_kind: NameKind) -> DeclaredName | None:
    """Return the name node binds, if any, as a var_kind when it is a variable."""
    if isinstance(node, DEFS):
        func_kind = NameKind.TEST_FUNC if is_test_func(node) else NameKind.FUNC
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


# An except alias and a mapping rest have no position of their own, so the name
# takes the clause header's end or the whole pattern's lines.
def _clause_binding(
    file: CheckInput, node: ast.AST, var_kind: NameKind
) -> DeclaredName | None:
    """Return the name an except alias or match pattern binds, if any."""
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


# Each type parameter has an annotation scope that global and nonlocal don't reach.
def _scope_key(name: DeclaredName, declared: set[str]) -> ast.AST | str | None:
    """Return name's key in its scope, or None if global or nonlocal moves it."""
    if isinstance(name.node, _TYPE_PARAMS):
        return name.node
    return None if name.text in declared else name.text
