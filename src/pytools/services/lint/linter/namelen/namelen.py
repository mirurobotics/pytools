import ast
from collections.abc import Iterator
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

MAX_NAME_LEN = 30
MAX_LOCAL_NAME_LEN = 20
MAX_TEST_NAME_LEN = 50

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
    scopes = [tree, *(node for node in ast.walk(tree) if isinstance(node, _SCOPES))]
    names = [name for scope in scopes for name in _first_bindings(scope)]
    return sorted(names, key=lambda name: name.line)


def _first_bindings(scope: ast.AST) -> list[_Name]:
    is_local = not isinstance(scope, ast.Module | ast.ClassDef)
    limit = MAX_LOCAL_NAME_LEN if is_local else MAX_NAME_LEN
    firsts: dict[str, _Name] = {}
    for node in _scope_nodes(scope):
        name = _binding(node, limit)
        if name is not None:
            firsts.setdefault(name.text, name)
    return list(firsts.values())


def _scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    # Yields in source order. A nested scope binds its name here, so it is
    # yielded but not entered.
    pending = list(ast.iter_child_nodes(scope))[::-1]
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, _SCOPES):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _binding(node: ast.AST, limit: int) -> _Name | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        is_test = node.name.startswith("test_")
        func_limit = MAX_TEST_NAME_LEN if is_test else MAX_NAME_LEN
        return _Name(node.name, node.lineno, func_limit)
    if isinstance(node, ast.ClassDef):
        return _Name(node.name, node.lineno, MAX_NAME_LEN)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return _Name(node.id, node.lineno, limit)
    if isinstance(node, ast.arg):
        return _Name(node.arg, node.lineno, limit)
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
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
