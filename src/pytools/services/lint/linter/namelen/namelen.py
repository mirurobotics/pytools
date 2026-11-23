import ast
from collections.abc import Iterator
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Rule,
    header_end,
    walk_outside,
)
from pytools.services.lint.linter.analysis.nolint import (
    has_def_nolint,
    has_nolint_on_lines,
)

_MAX_NAME_LEN = 30
_MAX_LOCAL_NAME_LEN = 20
_MAX_TEST_NAME_LEN = 50

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


@dataclass(frozen=True)
class _Name:
    text: str
    line: int
    limit: int
    node: ast.AST


def check(file: CheckInput) -> list[Diagnostic]:
    """Report names longer than their limit, at each one's first binding in a scope."""
    names = _declared_names(file.tree)
    diags = [_check_name(file, name) for name in names]
    return [diag for diag in diags if diag is not None]


def _declared_names(tree: ast.Module) -> list[_Name]:
    scopes: list[_Scope] = [tree]
    scopes += [node for node in ast.walk(tree) if isinstance(node, _SCOPES)]
    names = [name for scope in scopes for name in _first_bindings(scope)]
    return sorted(names, key=lambda name: name.line)


def _first_bindings(scope: _Scope) -> list[_Name]:
    is_local = not isinstance(scope, ast.Module | ast.ClassDef)
    limit = _MAX_LOCAL_NAME_LEN if is_local else _MAX_NAME_LEN
    nodes = list(_scope_nodes(_own_parts(scope)))
    declared = {
        name
        for node in nodes
        if isinstance(node, ast.Global | ast.Nonlocal)
        for name in node.names
    }
    found = [_binding(node, limit) for node in nodes]
    bindings = [name for name in found if name is not None]
    firsts: dict[ast.AST | str, _Name] = {}
    for name in sorted(bindings, key=lambda name: name.line):
        key = _scope_key(name, declared)
        if key is not None:
            firsts.setdefault(key, name)
    return list(firsts.values())


def _scope_key(name: _Name, declared: set[str]) -> ast.AST | str | None:
    # Each type parameter has an annotation scope of its own, which the body's
    # global and nonlocal statements don't reach.
    if isinstance(name.node, _TYPE_PARAMS):
        return name.node
    return None if name.text in declared else name.text


def _own_parts(scope: _Scope) -> list[ast.AST]:
    if isinstance(scope, ast.Module):
        return list(scope.body)
    if isinstance(scope, ast.ClassDef):
        return [*scope.type_params, *scope.body]
    if isinstance(scope, ast.Lambda):
        return [*_params(scope.args), scope.body]
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        return [*scope.type_params, *_params(scope.args), *scope.body]
    # Only a comprehension's loop targets are its own; a walrus in it binds
    # in the scope around it.
    return [gen.target for gen in scope.generators]


def _scope_nodes(nodes: list[ast.AST]) -> Iterator[ast.AST]:
    # A nested scope's name binds in the scope around it, and so do names in
    # its defaults, annotations, decorators and bases and a walrus in a
    # comprehension. A parameter is entered only through its outer parts.
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


def _binding(node: ast.AST, limit: int) -> _Name | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        is_test = node.name.startswith("test_")
        func_limit = _MAX_TEST_NAME_LEN if is_test else _MAX_NAME_LEN
        return _Name(node.name, node.lineno, func_limit, node)
    if isinstance(node, ast.ClassDef):
        return _Name(node.name, node.lineno, _MAX_NAME_LEN, node)
    if isinstance(node, _TYPE_PARAMS):
        return _Name(node.name, node.lineno, _MAX_LOCAL_NAME_LEN, node)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return _Name(node.id, node.lineno, limit, node)
    if isinstance(node, ast.arg):
        return _Name(node.arg, node.lineno, limit, node)
    return _clause_binding(node, limit)


def _clause_binding(node: ast.AST, limit: int) -> _Name | None:
    if isinstance(node, ast.ExceptHandler) and node.name:
        return _Name(node.name, node.lineno, limit, node)
    if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
        # The name ends a capture pattern, which can span lines.
        return _Name(node.name, node.end_lineno or node.lineno, limit, node)
    if isinstance(node, ast.MatchMapping) and node.rest:
        return _Name(node.rest, node.lineno, limit, node)
    return None


def _check_name(file: CheckInput, name: _Name) -> Diagnostic | None:
    length = len(name.text)
    if length <= name.limit:
        return None
    line = _name_line(file, name)
    if _has_nolint(file, name, line):
        return None
    message = f'name "{name.text}" is {length} chars (limit {name.limit})'
    return Diagnostic(file.path, line, message)


def _name_line(file: CheckInput, name: _Name) -> int:
    # An except alias has no position of its own; it ends the clause header.
    if isinstance(name.node, ast.ExceptHandler):
        return header_end(file, name.node)
    return name.line


def _has_nolint(file: CheckInput, name: _Name, line: int) -> bool:
    node = name.node
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return has_def_nolint(file, node, Rule.NAMELEN)
    last = line
    if isinstance(node, ast.MatchMapping):
        # A mapping rest has no position of its own either.
        last = node.end_lineno or line
    return has_nolint_on_lines(file.comments, Rule.NAMELEN, line, last)
