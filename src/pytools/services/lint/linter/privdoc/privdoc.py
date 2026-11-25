import ast
from collections.abc import Iterator
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
    Rule,
    function_body_lines,
    functions,
    is_code_line,
    module_header_end,
)
from pytools.services.lint.linter.analysis.comments import is_directive
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

_MESSAGE: Final = (
    "comment on identifier outside the exported API; "
    "only the exported API may be documented"
)


def check(file: CheckInput) -> list[Diagnostic]:
    """Report docstrings and comments on names outside the exported API."""
    private = list(_private_decls(file.tree.body, public=True))
    owners = [
        stmt
        for stmt in private
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    owners += _nested_owners(file.tree)
    docs = [_docstring_line(file, owner) for owner in owners]
    header = set(range(1, module_header_end(file) + 1))
    skipped = header | function_body_lines(file)
    attached = [_comment_groups(file, stmt, skipped) for stmt in private]
    prose = [_prose_line(file, group) for groups in attached for group in groups]
    lines = sorted({line for line in docs + prose if line is not None})
    return [Diagnostic(file.path, line, _MESSAGE) for line in lines]


def _private_decls(body: list[ast.stmt], *, public: bool) -> Iterator[ast.stmt]:
    for stmt in body:
        names = _declared_names(stmt)
        is_public = public and any(_is_public_name(name) for name in names)
        if names and not is_public:
            yield stmt
        if isinstance(stmt, ast.ClassDef):
            yield from _private_decls(stmt.body, public=is_public)


def _declared_names(stmt: ast.stmt) -> list[str]:
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [stmt.name]
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, ast.AnnAssign):
        targets = [stmt.target]
    elif isinstance(stmt, ast.TypeAlias):
        targets = [stmt.name]
    else:
        return []
    nodes = [node for target in targets for node in ast.walk(target)]
    names = [node for node in nodes if isinstance(node, ast.Name)]
    return [name.id for name in names if isinstance(name.ctx, ast.Store)]


def _is_public_name(name: str) -> bool:
    is_dunder = name.startswith("__") and name.endswith("__")
    return is_dunder or not name.startswith("_")


def _nested_owners(tree: ast.Module) -> list[Function | ast.ClassDef]:
    funcs = functions(tree)
    inner = {node for func in funcs for node in ast.walk(func) if node is not func}
    return [
        node
        for node in inner
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]


def _docstring_line(file: CheckInput, owner: Function | ast.ClassDef) -> int | None:
    first = owner.body[0]
    if not isinstance(first, ast.Expr) or ast.get_docstring(owner) is None:
        return None
    string = first.value
    end = string.end_lineno or string.lineno
    if has_nolint_on_lines(file.comments, Rule.PRIVDOC, string.lineno, end):
        return None
    return string.lineno


def _comment_groups(
    file: CheckInput, stmt: ast.stmt, skipped: set[int]
) -> list[list[int]]:
    decorators = (
        stmt.decorator_list
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        else []
    )
    anchors = [dec.lineno for dec in decorators] + [stmt.lineno]
    above = [_group_above(file, anchor, skipped) for anchor in anchors]
    trailing = [[anchor] for anchor in anchors if anchor in file.comments]
    return above + trailing


def _group_above(file: CheckInput, anchor: int, skipped: set[int]) -> list[int]:
    group: list[int] = []
    line = anchor - 1
    while line in file.comments and line not in skipped:
        if is_code_line(file, line):
            break
        group.insert(0, line)
        line -= 1
    return group


def _prose_line(file: CheckInput, group: list[int]) -> int | None:
    if not group:
        return None
    if has_nolint_on_lines(file.comments, Rule.PRIVDOC, group[0], group[-1]):
        return None
    prose = (line for line in group if not is_directive(file.comments[line].text))
    return next(prose, None)
