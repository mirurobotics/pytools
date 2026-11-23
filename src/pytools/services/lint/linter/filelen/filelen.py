from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Rule,
    is_code_line,
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
    numbers = range(1, len(file.lines) + 1)
    return sum(1 for number in numbers if is_code_line(file, number))


def _has_file_nolint(file: CheckInput) -> bool:
    last = start_line(file.tree.body[0])
    return has_nolint_on_lines(file.comments, Rule.FILELEN, 1, last)
