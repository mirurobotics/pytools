from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    body_lines,
    functions,
)
from pytools.services.lint.linter.analysis.comments import is_directive

_MESSAGE = "comments are not allowed inside function bodies"


def check(file: CheckInput) -> list[Diagnostic]:
    """Report each non-directive comment inside a function body."""
    bodies = [body_lines(file, func) for func in functions(file.tree)]
    inside = {number for body in bodies for number in body}
    lines = [number for number in sorted(file.comments) if number in inside]
    prose = [number for number in lines if not is_directive(file.comments[number].text)]
    return [Diagnostic(file.path, number, _MESSAGE) for number in prose]
