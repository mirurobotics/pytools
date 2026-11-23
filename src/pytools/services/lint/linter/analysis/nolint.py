import ast
import re

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    Rule,
    is_code_line,
    start_line,
)
from pytools.services.lint.linter.analysis.comments import Comment

_NOLINT = re.compile(r"#\s*nolint:([^#]*)")


def has_def_nolint(
    file: CheckInput, node: Function | ast.ClassDef, rule: Rule
) -> bool:
    """Report whether a nolint for rule sits on node's decorators or signature.

    A comment-only line just above them counts too.
    """
    first = start_line(node)
    if first > 1 and not is_code_line(file, first - 1):
        first -= 1
    return has_nolint_on_lines(file.comments, rule, first, _signature_end(file, node))


def _signature_end(file: CheckInput, node: Function | ast.ClassDef) -> int:
    line = start_line(node.body[0]) - 1
    while line > node.lineno and not is_code_line(file, line):
        line -= 1
    return max(line, node.lineno)


def has_nolint_on_lines(
    comments: dict[int, Comment], rule: Rule, first: int, last: int
) -> bool:
    """Report whether a nolint comment naming rule sits on a line in [first, last]."""
    return any(
        _is_nolint_for(comments[number].text, rule)
        for number in range(first, last + 1)
        if number in comments
    )


def _is_nolint_for(comment: str, rule: Rule) -> bool:
    match = _NOLINT.search(comment)
    if match is None:
        return False
    entries = (entry.split() for entry in match.group(1).split(","))
    return any(words[0] == rule for words in entries if words)
