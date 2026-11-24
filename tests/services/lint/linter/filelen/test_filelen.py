from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.filelen import filelen

type Parse = Callable[[str], CheckInput]

_THREE_LINES: Final = """\
a = 1
b = 2
c = 3
"""
_SHEBANG_COMMENTS_AND_BLANKS: Final = """\
#!/usr/bin/env python
# note

a = 1
    # indented
b = 2  # trailing

"""
_DOCSTRING: Final = """\
'''Doc.
More.
'''
a = 1
"""
_LIST: Final = """\
a = [
    1,
    2,
]
"""
_STRING: Final = """\
a = '''
text
'''
"""
_HASH_IN_STRING: Final = """\
a = '''
# not a comment
'''
"""
_NOLINT_ON_DOCSTRING_END: Final = """\
'''Doc.
'''  # nolint: filelen
b = 2
"""


def _over_limit() -> Diagnostic:
    return Diagnostic("a.py", 1, "file is 3 lines (limit 2)")


@pytest.mark.parametrize(
    ("max_len", "expected"),
    [
        pytest.param(4, [], id="under"),
        pytest.param(3, [], id="at"),
        pytest.param(2, [_over_limit()], id="over"),
    ],
)
def test_check_reports_files_over_the_limit(
    parse: Parse, max_len: int, expected: list[Diagnostic]
) -> None:
    assert filelen.check(parse(_THREE_LINES), max_len) == expected


def test_check_reports_file_without_statements(parse: Parse) -> None:
    diags = filelen.check(parse("\\\n\\\n\n"), 1)
    assert diags == [Diagnostic("a.py", 1, "file is 2 lines (limit 1)")]


def test_check_skips_nolint_file_without_statements(parse: Parse) -> None:
    assert filelen.check(parse("\\\n\\\n# nolint: filelen\n"), 1) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("# nolint: filelen\n" + _THREE_LINES, id="line-1"),
        pytest.param("\n# nolint: filelen\n\n" + _THREE_LINES, id="after-blank-line"),
        pytest.param(
            "a = 1  # nolint: filelen\nb = 2\nc = 3\n", id="first-statement-line"
        ),
    ],
)
def test_check_skips_file_with_nolint(parse: Parse, source: str) -> None:
    assert filelen.check(parse(source), 2) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("# nolint: other\n" + _THREE_LINES, id="other-rule"),
        pytest.param('a = "# nolint: filelen"\nb = 2\nc = 3\n', id="in-string"),
        pytest.param(
            "a = 1\nb = 2  # nolint: filelen\nc = 3\n", id="after-first-statement"
        ),
        pytest.param(_NOLINT_ON_DOCSTRING_END, id="docstring-closing-line"),
    ],
)
def test_check_reports_file_without_its_nolint(parse: Parse, source: str) -> None:
    assert filelen.check(parse(source), 2) == [_over_limit()]


@pytest.mark.parametrize(
    ("source", "count"),
    [
        pytest.param(_SHEBANG_COMMENTS_AND_BLANKS, 2, id="shebang-comments-blanks"),
        pytest.param(_DOCSTRING, 4, id="docstring"),
        pytest.param(_LIST, 4, id="list"),
        pytest.param(_STRING, 3, id="string"),
        pytest.param(_HASH_IN_STRING, 3, id="hash-in-string"),
    ],
)
def test_check_counts_code_lines(parse: Parse, source: str, count: int) -> None:
    diags = filelen.check(parse(source), 1)
    assert diags == [Diagnostic("a.py", 1, f"file is {count} lines (limit 1)")]
