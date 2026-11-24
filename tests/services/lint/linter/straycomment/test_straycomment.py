from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.straycomment import straycomment

type Parse = Callable[[str], CheckInput]

_BANNER: Final = """\
import os

# ----------------
# Helpers
# ----------------

def helper():
    pass
"""
_LOOSE_NOTES: Final = """\
class Point:
    first = 1

    # group of fields below

    second = 2


# more constants

LIMIT = 2
"""
_END_OF_FILE: Final = """\
def helper():
    pass

# TODO: more
"""
_ONE_LINE_DEF: Final = """\
def helper(): pass
# loose note
"""
_DIRECTIVE_THEN_PROSE: Final = """\
import os

# noqa: E402
# stray prose

LIMIT = 2
"""
_SIGNATURE: Final = """\
def helper(
    # first is documented.
    first,
):
    pass
"""
_LITERAL: Final = """\
LIMITS = [
    # the lower limit
    1,
]
"""
_ELSE: Final = """\
if ready:
    pass
# about else
else:
    pass
"""
_ELIF: Final = """\
if ready:
    pass
# about elif
elif done:
    pass
"""
_EXCEPT_FINALLY: Final = """\
try:
    pass
# about except
except OSError:
    pass
# about finally
finally:
    pass
"""
_CASE: Final = """\
match value:
    # about case
    case 1:
        pass
"""
_CLASS_TAIL: Final = """\
def helper():
    pass


class Point:
    first = 1

    # trailing note
"""
_ATTACHED: Final = """\
import os  # trailing

# Above a statement.
LIMIT = 1

# Above a decorator.
@cache
# Between the decorator and the def.
def helper():
    pass


class Point:
    # Above a field.
    first = 1  # trailing
"""
_HEADER: Final = """\
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026 Example.

# ruff: noqa: S101

import os
"""
_IF_UNDER_ELSE: Final = """\
if ready:
    pass
else:
    # Above an if, not an elif.
    if done:
        pass
"""
_FUNCTION_BODIES: Final = """\
def helper():
    first = 1

    # inside the body

    return first
    # trailing body note


class Point:
    def method(self):
        pass

        # trailing method note
"""
_HASH_IN_STRING: Final = """\
LABEL = "# not a comment"
TEXT = '''
# not a comment either
'''
"""
_MESSAGE: Final = (
    "comment is not attached to a statement; remove it or move it directly above one"
)


def _diags(*lines: int) -> list[Diagnostic]:
    return [Diagnostic("a.py", line, _MESSAGE) for line in lines]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_BANNER, _diags(3), id="banner-once-per-group"),
        pytest.param(_LOOSE_NOTES, _diags(4, 9), id="loose-notes"),
        pytest.param(_END_OF_FILE, _diags(4), id="end-of-file"),
        pytest.param(_ONE_LINE_DEF, _diags(2), id="after-one-line-def"),
    ],
)
def test_check_reports_stray_groups(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert straycomment.check(parse(source)) == expected


def test_check_reports_prose_after_directives(parse: Parse) -> None:
    assert straycomment.check(parse(_DIRECTIVE_THEN_PROSE)) == _diags(4)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_SIGNATURE, _diags(2), id="signature"),
        pytest.param(_LITERAL, _diags(2), id="multi-line-literal"),
    ],
)
def test_check_reports_comments_inside_statements(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert straycomment.check(parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_ELSE, _diags(3), id="else"),
        pytest.param(_ELIF, _diags(3), id="elif"),
        pytest.param(_EXCEPT_FINALLY, _diags(3, 6), id="except-finally"),
        pytest.param(_CASE, _diags(2), id="case"),
    ],
)
def test_check_reports_comments_above_clause_headers(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert straycomment.check(parse(source)) == expected


def test_check_reports_class_body_tail(parse: Parse) -> None:
    assert straycomment.check(parse(_CLASS_TAIL)) == _diags(8)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_ATTACHED, id="attached"),
        pytest.param("def helper(): pass  # trailing\n", id="one-line-def-trailing"),
        pytest.param(_IF_UNDER_ELSE, id="if-under-else"),
        pytest.param(_HEADER, id="module-header"),
        pytest.param("# a note\n# another note\n", id="comment-only-module"),
        pytest.param(_FUNCTION_BODIES, id="function-bodies"),
        pytest.param(_HASH_IN_STRING, id="hash-in-string"),
    ],
)
def test_check_skips_comments_that_are_not_stray(parse: Parse, source: str) -> None:
    assert straycomment.check(parse(source)) == []


@pytest.mark.parametrize(
    "directive",
    [
        "# noqa: E501",
        "# type: ignore",
        "# nolint: funclen",
        "# pragma: no cover",
        "# fmt: off",
        "# isort: skip_file",
        "# mypy: strict",
        "# ruff: noqa",
    ],
)
def test_check_skips_directive_only_groups(parse: Parse, directive: str) -> None:
    source = f"import os\n\n{directive}\n\nLIMIT = 1\n"
    assert straycomment.check(parse(source)) == []
