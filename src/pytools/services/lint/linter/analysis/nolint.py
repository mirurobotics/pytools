import ast
import re

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Rule,
    is_code_line,
)

type _Function = ast.FunctionDef | ast.AsyncFunctionDef

_NOLINT = re.compile(r"#\s*nolint:([^#]*)")


def has_def_nolint(file: CheckInput, func: _Function, rule: Rule) -> bool:
    """Report whether a nolint for rule sits on func's decorators or signature.

    A comment-only line just above them counts too.
    """
    first = _start_line(func)
    if first > 1 and not is_code_line(file.lines[first - 2]):
        first -= 1
    return has_nolint_on_lines(file.comments, rule, first, _signature_end(file, func))


def _start_line(node: ast.stmt) -> int:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return min((dec.lineno for dec in node.decorator_list), default=node.lineno)
    return node.lineno


def _signature_end(file: CheckInput, func: _Function) -> int:
    line = _start_line(func.body[0]) - 1
    while line > func.lineno and not is_code_line(file.lines[line - 1]):
        line -= 1
    return max(line, func.lineno)


def has_nolint_on_lines(
    comments: dict[int, str], rule: Rule, first: int, last: int
) -> bool:
    """Report whether a nolint comment naming rule sits on a line in [first, last]."""
    return any(
        _is_nolint_for(comments.get(number, ""), rule)
        for number in range(first, last + 1)
    )


def _is_nolint_for(comment: str, rule: Rule) -> bool:
    match = _NOLINT.search(comment)
    if match is None:
        return False
    entries = (entry.split() for entry in match.group(1).split(","))
    return any(words[0] == rule for words in entries if words)
