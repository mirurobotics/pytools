from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funclen import funclen

Parse = Callable[[str], CheckInput]

_THREE_LINES = """\
def f():
    a = 1
    b = 2
    c = 3
"""
_NESTED = """\
def outer():
    def inner():
        a = 1
        b = 2

    return inner
"""
_NOLINT_ON_DEF_LINE = """\
def f():  # nolint: funclen
    a = 1
    b = 2
    c = 3
"""
_DOCSTRING = """\
def f():
    '''Doc.

    More.
    '''
    a = 1
    b = 2
"""
_BLANK_AND_COMMENT_LINES = """\
def f():
    a = 1

    # note
    b = 2
"""
_LIST = """\
def f():
    a = [
        1,
        2,
    ]
    return a
"""
_DICT = """\
def f():
    a = {
        1: 2,
    }
    return a
"""
_STRING = """\
def f():
    a = '''
    text
    '''
    return a
"""
_CLOSING_LINE_STARTS_LITERAL = """\
def f():
    g([
        1,
    ], [
        2,
    ])
"""
_CALL_ARGS = """\
def f():
    g(
        1,
    )
"""
_ASYNC = """\
async def f():
    await g()
    await h()
"""
_DOCSTRING_ONLY = """\
def f():
    '''Doc.'''
"""


@pytest.mark.parametrize(
    ("max_len", "expected"),
    [
        pytest.param(4, [], id="under"),
        pytest.param(3, [], id="at"),
        pytest.param(
            2, [Diagnostic("a.py", 1, "function f is 3 lines (limit 2)")], id="over"
        ),
        pytest.param(0, [], id="zero-disables"),
        pytest.param(-1, [], id="negative-disables"),
    ],
)
def test_check_reports_functions_over_the_limit(
    parse: Parse, max_len: int, expected: list[Diagnostic]
) -> None:
    assert funclen.check(parse(_THREE_LINES), max_len) == expected


def test_check_reports_nested_functions_in_line_order(parse: Parse) -> None:
    assert funclen.check(parse(_NESTED), 1) == [
        Diagnostic("a.py", 1, "function outer is 4 lines (limit 1)"),
        Diagnostic("a.py", 2, "function inner is 2 lines (limit 1)"),
    ]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_NOLINT_ON_DEF_LINE, id="def-line"),
        pytest.param("# nolint: funclen\n" + _THREE_LINES, id="line-above"),
        pytest.param(
            "# nolint: funclen\n@decorator\n" + _THREE_LINES, id="above-decorators"
        ),
    ],
)
def test_check_skips_function_with_nolint(parse: Parse, source: str) -> None:
    assert funclen.check(parse(source), 2) == []


@pytest.mark.parametrize(
    ("prefix", "line"),
    [
        pytest.param("# nolint: other\n", 2, id="other-rule"),
        pytest.param('x = "# nolint: funclen"\n', 2, id="in-string"),
        pytest.param("# nolint: funclen\n\n", 3, id="two-lines-above"),
        pytest.param("@decorator\n", 2, id="decorated"),
    ],
)
def test_check_reports_function_without_its_nolint(
    parse: Parse, prefix: str, line: int
) -> None:
    diags = funclen.check(parse(prefix + _THREE_LINES), 2)
    assert diags == [Diagnostic("a.py", line, "function f is 3 lines (limit 2)")]


@pytest.mark.parametrize(
    ("source", "count"),
    [
        pytest.param(_DOCSTRING, 2, id="docstring"),
        pytest.param(_BLANK_AND_COMMENT_LINES, 2, id="blank-and-comment-lines"),
        pytest.param(_LIST, 2, id="list"),
        pytest.param(_DICT, 2, id="dict"),
        pytest.param(_STRING, 2, id="string"),
        pytest.param(_CLOSING_LINE_STARTS_LITERAL, 2, id="closing-line-starts-code"),
        pytest.param(_CALL_ARGS, 3, id="call-args"),
        pytest.param(_ASYNC, 2, id="async"),
    ],
)
def test_check_counts_code_lines(parse: Parse, source: str, count: int) -> None:
    diags = funclen.check(parse(source), 1)
    assert diags == [Diagnostic("a.py", 1, f"function f is {count} lines (limit 1)")]


def test_check_ignores_docstring_only_function(parse: Parse) -> None:
    assert funclen.check(parse(_DOCSTRING_ONLY), 1) == []
