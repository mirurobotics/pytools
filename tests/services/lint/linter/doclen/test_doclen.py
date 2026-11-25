import dataclasses
from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.doclen import doclen

type Parse = Callable[[str], CheckInput]

_THREE_LINES: Final = """\
def f():
    '''One.
    Two.
    Three.
    '''
"""
_OWNERS: Final = """\
'''Module.
More.'''

class Outer:
    '''Outer.
    More.'''

    def method(self):
        '''Method.
        More.'''

        class Inner:
            '''Inner.
            More.'''

async def run():
    '''Run.
    More.'''

    def helper():
        '''Helper.
        More.'''
"""
_INNER_BLANK_LINE: Final = """\
def f():
    '''Doc.

    More.
    '''
"""
_OUTER_BLANK_LINES: Final = """\
def f():
    '''

    Doc.
    More.

    '''
"""
_NOT_DOCSTRINGS: Final = """\
x = 1
'''Not a
docstring.'''

def f():
    x = 1
    '''Not a
    docstring.'''

class C:
    name = '''Not a
    docstring.'''

def g():
    f'''Not a
    docstring.'''

def h():
    b'''Not a
    docstring.'''
"""
_PACKAGE: Final = """\
'''Package.
More.
Most.'''

def f():
    '''F.
    More.'''
"""


@pytest.mark.parametrize(
    ("max_lines", "expected"),
    [
        pytest.param(4, [], id="under"),
        pytest.param(3, [], id="at"),
        pytest.param(
            2, [Diagnostic("a.py", 2, "docstring is 3 lines (limit 2)")], id="over"
        ),
    ],
)
def test_check_reports_docstrings_over_the_limit(
    parse: Parse, max_lines: int, expected: list[Diagnostic]
) -> None:
    assert doclen.check(parse(_THREE_LINES), max_lines, 20) == expected


def test_check_reports_every_docstring_in_line_order(parse: Parse) -> None:
    diags = doclen.check(parse(_OWNERS), 1, 20)
    assert diags == [
        Diagnostic("a.py", line, "docstring is 2 lines (limit 1)")
        for line in [1, 5, 9, 13, 17, 21]
    ]


@pytest.mark.parametrize(
    ("source", "count"),
    [
        pytest.param(_INNER_BLANK_LINE, 3, id="inner-blank-line"),
        pytest.param(_OUTER_BLANK_LINES, 2, id="outer-blank-lines"),
    ],
)
def test_check_counts_cleaned_lines(parse: Parse, source: str, count: int) -> None:
    diags = doclen.check(parse(source), 1, 20)
    assert diags == [Diagnostic("a.py", 2, f"docstring is {count} lines (limit 1)")]


def test_check_skips_strings_that_are_not_docstrings(parse: Parse) -> None:
    assert doclen.check(parse(_NOT_DOCSTRINGS), 1, 20) == []


@pytest.mark.parametrize(
    ("path", "max_package_lines", "expected"),
    [
        pytest.param("pkg/__init__.py", 3, [], id="package-at-its-limit"),
        pytest.param(
            "pkg/__init__.py",
            2,
            [Diagnostic("pkg/__init__.py", 1, "docstring is 3 lines (limit 2)")],
            id="package-over-its-limit",
        ),
        pytest.param(
            "pkg/mod.py",
            3,
            [Diagnostic("pkg/mod.py", 1, "docstring is 3 lines (limit 1)")],
            id="module",
        ),
    ],
)
def test_check_gives_package_docstring_its_own_limit(
    parse: Parse, path: str, max_package_lines: int, expected: list[Diagnostic]
) -> None:
    file = dataclasses.replace(parse(_PACKAGE), path=path)
    function_diag = Diagnostic(path, 6, "docstring is 2 lines (limit 1)")
    diags = doclen.check(file, 1, max_package_lines)
    assert diags == [*expected, function_diag]
