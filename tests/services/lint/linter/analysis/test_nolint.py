import pytest

from pytools.services.lint.linter.analysis.analysis import Rule
from pytools.services.lint.linter.analysis.comments import Comment
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines


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
    assert has_nolint_on_lines({1: comment}, Rule.FUNCLEN, 1, 1) is expected
