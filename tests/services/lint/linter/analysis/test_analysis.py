from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    functions,
    is_code_line,
)

Parse = Callable[[str], CheckInput]

_FUNCTIONS = """\
class A:
    def method(self):
        def inner():
            pass


async def b():
    pass


def c():
    pass
"""
_SOURCE = """\
a = 1

    # comment
b = 2  # trailing
c = '''
# not a comment
'''
# spaced \t
"""


def test_diagnostic_str() -> None:
    diag = Diagnostic(path="src/a.py", line=42, message="function f is 31 lines")
    assert str(diag) == "src/a.py:42: function f is 31 lines"


def test_functions_lists_nested_and_async_in_line_order(parse: Parse) -> None:
    names = [func.name for func in functions(parse(_FUNCTIONS).tree)]
    assert names == ["method", "inner", "b", "c"]


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        pytest.param(1, True, id="code"),
        pytest.param(2, False, id="blank"),
        pytest.param(3, False, id="comment-only"),
        pytest.param(4, True, id="trailing-comment"),
        pytest.param(6, True, id="hash-in-string"),
        pytest.param(8, False, id="comment-with-trailing-whitespace"),
    ],
)
def test_is_code_line(parse: Parse, number: int, expected: bool) -> None:
    assert is_code_line(parse(_SOURCE), number) is expected
