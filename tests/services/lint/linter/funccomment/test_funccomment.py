from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funccomment import funccomment

type Parse = Callable[[str], CheckInput]

_COMMENT_LINE: Final = """\
def helper():
    # explain
    first = 1
    return first
"""
_TRAILING: Final = """\
def helper():
    first = 1  # trailing
    return first
"""
_NESTED: Final = """\
def outer():
    def inner():
        # in a nested def
        pass

    class Point:
        # in a class in a body
        first = 1

    return inner, Point
"""
_TAIL: Final = """\
def helper():
    return 1
    # after the last statement

LIMIT = 1
"""
_BEFORE_DOCSTRING: Final = """\
def helper():
    # before the docstring
    '''Do a thing.'''
"""
_SIGNATURE: Final = """\
def helper(
    # first is documented.
    first,
):
    return first
"""
_ONE_LINE_DEF: Final = """\
def helper(): pass  # trailing
# after the def
"""
_WRAPPED_ONE_LINE_DEF: Final = """\
def helper(
    first,
): return first  # trailing
"""
_MODULE_AND_CLASS: Final = """\
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
_NEXT_METHOD: Final = """\
class Point:
    def first(self):
        pass

    # about second
    def second(self):
        pass
"""
_HASH_IN_STRING: Final = """\
def helper():
    label = "# not a comment"
    return label
"""
_MESSAGE: Final = "comments are not allowed inside function bodies"


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
        pytest.param(_WRAPPED_ONE_LINE_DEF, id="wrapped-one-line-def"),
        pytest.param(_MODULE_AND_CLASS, id="module-and-class"),
        pytest.param(_NEXT_METHOD, id="above-next-method"),
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
@pytest.mark.parametrize(
    "template",
    [
        pytest.param("def helper():\n    {}\n    return 1\n", id="own-line"),
        pytest.param("def helper():\n    return 1  {}\n", id="trailing"),
    ],
)
def test_check_skips_directives(parse: Parse, directive: str, template: str) -> None:
    source = template.format(directive)
    assert funccomment.check(parse(source)) == []


def test_check_skips_hash_in_string(parse: Parse) -> None:
    assert funccomment.check(parse(_HASH_IN_STRING)) == []
