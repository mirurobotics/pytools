import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    elif_branch,
    function_body_lines,
    is_code_line,
    line_groups,
    module_header_end,
)
from pytools.services.lint.linter.analysis.comments import is_directive

_MESSAGE: Final = (
    "comment is not attached to a statement; remove it or move it directly above one"
)


def check(file: CheckInput) -> list[Diagnostic]:
    """Report comment groups outside functions that sit directly above no statement."""
    starts = _statement_starts(file.tree)
    groups = line_groups(_candidate_lines(file))
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
    header = set(range(1, module_header_end(file) + 1))
    skipped = header | function_body_lines(file)
    outside = [number for number in sorted(file.comments) if number not in skipped]
    return [number for number in outside if not is_code_line(file, number)]


def _first_prose(file: CheckInput, group: list[int]) -> int | None:
    prose = (number for number in group if not is_directive(file.comments[number].text))
    return next(prose, None)
