import ast
from collections.abc import Iterator
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Rule,
    walk_outside,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

_MAX_NAME_LEN = 30
_MAX_LOCAL_NAME_LEN = 20
_MAX_TEST_NAME_LEN = 50

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
    found = [_binding(node, limit) for node in _scope_nodes(_own_parts(scope))]
    bindings = [name for name in found if name is not None]
    firsts: dict[str, _Name] = {}
    for name in sorted(bindings, key=lambda name: name.line):
        firsts.setdefault(name.text, name)
    return list(firsts.values())


def _own_parts(scope: _Scope) -> list[ast.AST]:
    if isinstance(scope, ast.Module | ast.ClassDef):
        return list(scope.body)
    if isinstance(scope, ast.Lambda):
        return [*_params(scope.args), scope.body]
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        return [*_params(scope.args), *scope.body]
    # Only a comprehension's loop targets are its own; a walrus in it binds
    # in the scope around it.
    return [gen.target for gen in scope.generators]


def _scope_nodes(nodes: list[ast.AST]) -> Iterator[ast.AST]:
    # A nested scope's name, and the parts of it Python runs in the scope
    # around it, belong to that outer scope.
    for node in walk_outside(nodes, _SCOPES):
        yield node
        if isinstance(node, _SCOPES):
            yield from _scope_nodes(_outer_parts(node))


def _outer_parts(scope: _Nested) -> list[ast.AST]:
    if isinstance(scope, ast.ClassDef):
        return [*scope.decorator_list, *scope.bases, *scope.keywords]
    if isinstance(scope, ast.Lambda):
        return _defaults(scope.args)
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        return [*scope.decorator_list, *_defaults(scope.args)]
    if isinstance(scope, ast.DictComp):
        elements = [scope.key, scope.value]
    else:
        elements = [scope.elt]
    tests = [part for gen in scope.generators for part in (gen.iter, *gen.ifs)]
    return [*elements, *tests]


def _params(args: ast.arguments) -> list[ast.AST]:
    params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
    return [param for param in params if param is not None]


def _defaults(args: ast.arguments) -> list[ast.AST]:
    return [default for default in (*args.defaults, *args.kw_defaults) if default]


def _binding(node: ast.AST, limit: int) -> _Name | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        is_test = node.name.startswith("test_")
        func_limit = _MAX_TEST_NAME_LEN if is_test else _MAX_NAME_LEN
        return _Name(node.name, node.lineno, func_limit)
    if isinstance(node, ast.ClassDef):
        return _Name(node.name, node.lineno, _MAX_NAME_LEN)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return _Name(node.id, node.lineno, limit)
    if isinstance(node, ast.arg):
        return _Name(node.arg, node.lineno, limit)
    if isinstance(node, ast.ExceptHandler) and node.name and node.type:
        # The name follows the exception type, which can span lines.
        return _Name(node.name, node.type.end_lineno or node.lineno, limit)
    if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
        return _Name(node.name, node.lineno, limit)
    if isinstance(node, ast.MatchMapping) and node.rest:
        return _Name(node.rest, node.lineno, limit)
    return None


def _check_name(file: CheckInput, name: _Name) -> Diagnostic | None:
    length = len(name.text)
    if length <= name.limit:
        return None
    if has_nolint_on_lines(file.comments, Rule.NAMELEN, name.line, name.line):
        return None
    message = f'name "{name.text}" is {length} chars (limit {name.limit})'
    return Diagnostic(file.path, name.line, message)
