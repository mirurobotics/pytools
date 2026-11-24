from typing import Final

import pytest

from pytools.services.lint.linter.analysis.comments import (
    Comment,
    collect_comments,
    is_directive,
)

_SOURCE: Final = """\
# top
x = "# not a comment"  # trailing

def f():
    # inside
    return 1
# spaced \t
"""


def test_collect_comments_maps_lines_to_comments() -> None:
    assert collect_comments(_SOURCE) == {
        1: Comment(0, "# top"),
        2: Comment(23, "# trailing"),
        5: Comment(4, "# inside"),
        7: Comment(0, "# spaced \t"),
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("# noqa", True, id="bare-noqa"),
        pytest.param("#noqa: E501", True, id="no-space"),
        pytest.param("# NOQA: E501", True, id="upper-case-noqa"),
        pytest.param("# type: ignore  # reason", True, id="directive-then-reason"),
        pytest.param("# ruff: noqa", True, id="keyword-colon"),
        pytest.param("# pylint: disable=too-many-lines", True, id="pylint"),
        pytest.param("# pyright: reportPrivateUsage=false", True, id="pyright"),
        pytest.param("# nosec", True, id="bare-nosec"),
        pytest.param("# nosec B602, B607", True, id="nosec-codes"),
        pytest.param("# noqaish", False, id="noqa-prefix"),
        pytest.param("# nosecret", False, id="nosec-prefix"),
        pytest.param("# type ignore", False, id="keyword-without-colon"),
        pytest.param("# see # noqa", False, id="directive-not-first"),
        pytest.param("# explain", False, id="prose"),
    ],
)
def test_is_directive(text: str, expected: bool) -> None:
    assert is_directive(text) is expected
