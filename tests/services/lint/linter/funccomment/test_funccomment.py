from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funccomment import funccomment

Parse = Callable[[str], CheckInput]

_COMMENT_LINE = """\
def helper():
    # explain
    first = 1
    return first
"""
_TRAILING = """\
def helper():
    first = 1  # trailing
    return first
"""
_NESTED = """\
def outer():
    def inner():
        # in a nested def
        pass

    class Point:
        # in a class in a body
        first = 1

    return inner, Point
"""
_TAIL = """\
def helper():
    return 1
    # after the last statement

LIMIT = 1
"""
_BEFORE_DOCSTRING = """\
def helper():
    # before the docstring
    '''Do a thing.'''
"""
_SIGNATURE = """\
def helper(
    # first is documented.
    first,
):
    return first
"""
_ONE_LINE_DEF = """\
def helper(): pass  # trailing
# after the def
"""
_MODULE_AND_CLASS = """\
# above a function
def helper():
    pass


class Point:
    # above a field
    first = 1

    # above a method
    def method(self):
        pass
"""
_HASH_IN_STRING = """\
def helper():
    label = "# not a comment"
    return label
"""
_MESSAGE = "comments are not allowed inside function bodies"


def _diags(*lines: int) -> list[Diagnostic]:
    return [Diagnostic("a.py", line, _MESSAGE) for line in lines]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_COMMENT_LINE, _diags(2), id="comment-line"),
        pytest.param(_TRAILING, _diags(2), id="trailing"),
        pytest.param(_NESTED, _diags(3, 7), id="nested-def-and-class"),
        pytest.param(_TAIL, _diags(3), id="indented-tail"),
        pytest.param(_BEFORE_DOCSTRING, _diags(2), id="before-docstring"),
    ],
)
def test_check_reports_body_comments(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funccomment.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_SIGNATURE, id="signature"),
        pytest.param("def helper():  # note\n    pass\n", id="header-line"),
        pytest.param(_ONE_LINE_DEF, id="one-line-def"),
        pytest.param(_MODULE_AND_CLASS, id="module-and-class"),
    ],
)
def test_check_skips_comments_outside_bodies(parse: Parse, source: str) -> None:
    assert funccomment.check(parse(source)) == []


@pytest.mark.parametrize(
    "directive",
    [
        "# noqa: E501",
        "# type: ignore",
        "# type: ignore  # reason",
        "# nolint: funclen",
        "# pragma: no cover",
        "# fmt: off",
        "# isort: skip_file",
        "# mypy: strict",
        "# ruff: noqa",
    ],
)
def test_check_skips_directives(parse: Parse, directive: str) -> None:
    source = f"def helper():\n    {directive}\n    return 1\n"
    assert funccomment.check(parse(source)) == []


def test_check_skips_hash_in_string(parse: Parse) -> None:
    assert funccomment.check(parse(_HASH_IN_STRING)) == []
