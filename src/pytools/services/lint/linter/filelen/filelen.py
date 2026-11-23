from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Rule,
    start_line,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines


def check(file: CheckInput, max_len: int) -> list[Diagnostic]:
    """Report the file if it has over max_len non-blank, non-comment lines."""
    count = _count_lines(file)
    if count <= max_len:
        return []
    if _has_file_nolint(file):
        return []
    message = f"file is {count} lines (limit {max_len})"
    return [Diagnostic(file.path, 1, message)]


def _count_lines(file: CheckInput) -> int:
    code_lines = [
        line
        for number, line in enumerate(file.lines, start=1)
        if _strip_comment(line, file.comments.get(number)).strip()
    ]
    return len(code_lines)


def _strip_comment(line: str, comment: str | None) -> str:
    if comment is None:
        return line
    return line[: line.rfind(comment)]


def _has_file_nolint(file: CheckInput) -> bool:
    last = start_line(file.tree.body[0])
    return has_nolint_on_lines(file.comments, Rule.FILELEN, 1, last)
