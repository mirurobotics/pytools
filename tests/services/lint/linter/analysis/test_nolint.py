from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Rule
from pytools.services.lint.linter.analysis.comments import Comment
from pytools.services.lint.linter.analysis.names import declared_names
from pytools.services.lint.linter.analysis.nolint import (
    has_name_nolint,
    has_nolint_on_lines,
)

type Parse = Callable[[str], CheckInput]

_MAPPING_REST: Final = """\
match a:
    case {
        **name  # nolint: varname
    }:
        pass
"""
_WRAPPED_DEF: Final = """\
def name(
    first,
): return first  # nolint: varname
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("name = 1  # nolint: varname\n", True, id="binding-line"),
        pytest.param("# nolint: varname\nname = 1\n", False, id="line-above-binding"),
        pytest.param(_MAPPING_REST, True, id="mapping-rest-pattern"),
        pytest.param(
            "# nolint: varname\ndef name():\n    pass\n", True, id="line-above-def"
        ),
        pytest.param(_WRAPPED_DEF, True, id="wrapped-def-same-line-body"),
    ],
)
def test_has_name_nolint_searches_the_name_lines(
    parse: Parse, source: str, expected: bool
) -> None:
    file = parse(source)
    name = declared_names(file)[0]
    assert has_name_nolint(file, name, Rule.VARNAME) is expected


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        pytest.param(2, 3, True, id="range-ends-on-comment"),
        pytest.param(3, 4, True, id="range-starts-on-comment"),
        pytest.param(1, 2, False, id="range-before-comment"),
        pytest.param(4, 5, False, id="range-after-comment"),
    ],
)
def test_has_nolint_on_lines_searches_the_range(
    first: int, last: int, expected: bool
) -> None:
    comments = {3: Comment(0, "# nolint: funclen")}
    assert has_nolint_on_lines(comments, Rule.FUNCLEN, first, last) is expected


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        ("# nolint: funclen", True),
        ("#nolint:funclen", True),
        ("# nolint: other, funclen", True),
        ("# nolint: funclen  # reason", True),
        ("# nolint: funclen reason", True),
        ("# noqa: E501  # nolint: funclen", True),
        ("# nolint: other", False),
        ("# nolint: funclens", False),
        ("# nolint: other  # funclen", False),
        ("# nolint:", False),
        ("# remove nolint: funclen later", False),
        ("# funclen", False),
    ],
)
def test_has_nolint_on_lines_matches_rule(comment: str, expected: bool) -> None:
    comments = {1: Comment(0, comment)}
    assert has_nolint_on_lines(comments, Rule.FUNCLEN, 1, 1) is expected
