from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    is_code_line,
)

Parse = Callable[[str], CheckInput]

_SOURCE = """\
a = 1

    # comment
b = 2  # trailing
c = '''
# not a comment
'''
"""


def test_diagnostic_str() -> None:
    diag = Diagnostic(path="src/a.py", line=42, message="function f is 31 lines")
    assert str(diag) == "src/a.py:42: function f is 31 lines"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        pytest.param(1, True, id="code"),
        pytest.param(2, False, id="blank"),
        pytest.param(3, False, id="comment-only"),
        pytest.param(4, True, id="trailing-comment"),
        pytest.param(6, True, id="hash-in-string"),
    ],
)
def test_is_code_line(parse: Parse, number: int, expected: bool) -> None:
    assert is_code_line(parse(_SOURCE), number) is expected
