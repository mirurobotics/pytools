from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    function_body_lines,
)
from pytools.services.lint.linter.analysis.comments import is_directive

_MESSAGE: Final = "comments are not allowed inside function bodies"


def check(file: CheckInput) -> list[Diagnostic]:
    """Report each non-directive comment inside a function body."""
    inside = function_body_lines(file)
    lines = [number for number in sorted(file.comments) if number in inside]
    prose = [number for number in lines if not is_directive(file.comments[number].text)]
    return [Diagnostic(file.path, number, _MESSAGE) for number in prose]
