import dataclasses
from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.rules import Config, run_checks

type Parse = Callable[[str], CheckInput]

_SOURCE: Final = """\
def f(parameter_name_too_long, n):
    if a:
        if b:
            pass  # in body

# f(n)

total = 0

def _g():
    f()

assert x.a == 1
assert x.b == 2
assert x.c == 3

def _documented():
    '''Documented.
    It is documented.
    '''
"""
_PACKAGE_DOC: Final = """\
'''Doc.
More.'''
"""


@pytest.mark.parametrize(
    "exclude",
    [
        pytest.param(frozenset(), id="none"),
        *(pytest.param(frozenset({rule}), id=rule) for rule in Rule),
    ],
)
def test_run_checks_honors_exclude(parse: Parse, exclude: frozenset[Rule]) -> None:
    config = Config(
        max_func_len=1,
        max_file_len=1,
        max_nest_depth=1,
        max_doc_lines=1,
        exclude=exclude,
    )
    expected = [diag for rule, diag in _diagnostics().items() if rule not in exclude]
    assert run_checks(parse(_SOURCE), config) == expected


def _diagnostics() -> dict[Rule, Diagnostic]:
    return {
        Rule.FUNCLEN: Diagnostic("a.py", 1, "function f is 3 lines (limit 1)"),
        Rule.FILELEN: Diagnostic("a.py", 1, "file is 14 lines (limit 1)"),
        Rule.NESTDEPTH: Diagnostic(
            "a.py",
            3,
            "nesting depth is 2 (limit 1) — consider early returns or extracting"
            " a helper",
        ),
        Rule.NAMELEN: Diagnostic(
            "a.py", 1, 'name "parameter_name_too_long" is 23 chars (limit 20)'
        ),
        Rule.VARNAME: Diagnostic(
            "a.py",
            1,
            'variable name "n" is shorter than 3 chars; use a descriptive name',
        ),
        Rule.STRAYCOMMENT: Diagnostic(
            "a.py",
            6,
            "comment is not attached to a statement; remove it or move it directly"
            " above one",
        ),
        Rule.FUNCCOMMENT: Diagnostic(
            "a.py", 4, "comments are not allowed inside function bodies"
        ),
        Rule.COMMENTEDCODE: Diagnostic(
            "a.py", 6, "commented-out code; delete it instead"
        ),
        Rule.MUTABLEGLOBAL: Diagnostic(
            "a.py",
            8,
            "mutable global variable: use a Final constant, a type statement"
            " or a function instead",
        ),
        Rule.FUNCORDER: Diagnostic(
            "a.py", 1, '"f" should be below its last caller "_g"'
        ),
        Rule.FIELDASSERT: Diagnostic(
            "a.py",
            13,
            "3 asserts compare fields of x one at a time; compare the whole value"
            " in one assert, or move the checks into a helper that takes x",
        ),
        Rule.DOCLEN: Diagnostic("a.py", 18, "docstring is 2 lines (limit 1)"),
        Rule.DOCRESTATE: Diagnostic(
            "a.py",
            18,
            "docstring for _documented only restates its name; say what it does"
            " or remove it",
        ),
    }


def test_run_checks_passes_the_package_doc_limit(parse: Parse) -> None:
    file = dataclasses.replace(parse(_PACKAGE_DOC), path="pkg/__init__.py")
    exclude = frozenset(Rule) - {Rule.DOCLEN}
    config = Config(max_doc_lines=3, max_package_doc_lines=1, exclude=exclude)
    diag = Diagnostic("pkg/__init__.py", 1, "docstring is 2 lines (limit 1)")
    assert run_checks(file, config) == [diag]
