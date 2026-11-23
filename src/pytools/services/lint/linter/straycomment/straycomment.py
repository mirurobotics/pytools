import ast

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
    elif_branch,
    functions,
    header_end,
    is_code_line,
    module_header_end,
)
from pytools.services.lint.linter.analysis.comments import is_directive

_MESSAGE = (
    "comment is not attached to a statement; remove it or move it directly above one"
)


def check(file: CheckInput) -> list[Diagnostic]:
    """Report comment groups outside functions that sit directly above no statement."""
    starts = _statement_starts(file.tree)
    groups = _groups(_candidate_lines(file))
    stray = [group for group in groups if group[-1] + 1 not in starts]
    lines = [_first_prose(file, group) for group in stray]
    return [Diagnostic(file.path, line, _MESSAGE) for line in lines if line is not None]


def _statement_starts(tree: ast.Module) -> set[int]:
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.stmt)]
    decorators = [
        dec
        for node in nodes
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        for dec in node.decorator_list
    ]
    branches = [elif_branch(node) for node in nodes if isinstance(node, ast.If)]
    elifs = {branch.lineno for branch in branches if branch is not None}
    starts = {node.lineno for node in nodes} | {dec.lineno for dec in decorators}
    return starts - elifs


def _candidate_lines(file: CheckInput) -> list[int]:
    skipped = set(range(1, module_header_end(file) + 1))
    for func in functions(file.tree):
        skipped.update(_body_lines(file, func))
    outside = [number for number in sorted(file.comments) if number not in skipped]
    return [number for number in outside if not is_code_line(file, number)]


def _body_lines(file: CheckInput, func: Function) -> range:
    # A comment indented under the def after its last statement is still in
    # its body.
    end = func.end_lineno or func.lineno
    while end < len(file.lines) and _is_body_tail(file, end + 1, func.col_offset):
        end += 1
    return range(header_end(file, func) + 1, end + 1)


def _is_body_tail(file: CheckInput, number: int, indent: int) -> bool:
    if is_code_line(file, number):
        return False
    comment = file.comments.get(number)
    return comment is None or comment.column > indent


def _groups(lines: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for number in lines:
        if groups and groups[-1][-1] == number - 1:
            groups[-1].append(number)
        else:
            groups.append([number])
    return groups


def _first_prose(file: CheckInput, group: list[int]) -> int | None:
    prose = (
        number for number in group if not is_directive(file.comments[number].text)
    )
    return next(prose, None)
