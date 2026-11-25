from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.privdoc import privdoc

type Parse = Callable[[str], CheckInput]

_PRIVATE_OWNERS: Final = """\
def _run():
    '''Run.'''

class _Client:
    '''A client.'''

    def close(self):
        '''Close it.'''

    def __init__(self):
        '''Set it up.'''
"""
_PRIVATE_MEMBERS: Final = """\
class Client:
    def _close(self):
        '''Close it.'''

    # The cache.
    _cache = {}
"""
_NESTED: Final = """\
def run():
    def helper():
        '''Help.'''

    class Inner:
        '''The inner class.'''
"""
_PUBLIC: Final = """\
'''The module.'''

LIMIT = 1  # The limit.

# Run it.
def run():
    '''Run.'''

class Client:
    '''A client.'''

    # The name.
    name = 1

    def __init__(self):
        '''Set it up.'''
"""
_NOT_DOCSTRINGS: Final = """\
def _run():
    x = 1
    '''Run.'''

def _stop():
    f'''Stop.'''
"""
_COMMENTS: Final = """\
import os

# The limit.
# More.
_LIMIT = 1

_TIMEOUT = 2  # Seconds.

# About run.
def _run():  # Trailing.
    pass
"""
_DIRECTIVES: Final = """\
import os

# noqa: E402
_LIMIT = 1

# type: ignore
# The timeout.
_TIMEOUT = 2
"""
_FUNCTION_BODY: Final = """\
def run():
    # Body.
    _limit = 1

    # Above helper.
    def _helper():
        pass
"""
_HEADER: Final = """\
#!/usr/bin/env python3
# Copyright.
_LIMIT = 1

# The timeout.
_TIMEOUT = 2
"""
_DECORATED: Final = """\
import os

# Above.
@cache
# Between.
@other
# Last.
def _run():
    pass
"""
_DECORATED_FIRST: Final = """\
@cache
# Between.
def _run():
    pass
"""
_NOLINT: Final = """\
def _run():
    '''Run.'''  # nolint: privdoc
"""
_NOLINT_ON_CLOSING_LINE: Final = """\
def _run():
    '''Run.
    Runs.
    '''  # nolint: privdoc
"""
_NOLINT_FOR_OTHER_RULE: Final = """\
def _run():
    '''Run.'''  # nolint: funclen
"""
_NOLINT_ON_DEF_LINE: Final = """\
def _run():  # nolint: privdoc
    '''Run.'''
"""
_NOLINT_IN_GROUP: Final = """\
import os

# The limit.
# nolint: privdoc
_LIMIT = 1
"""
_NOLINT_TRAILING: Final = """\
import os

# The limit.
_LIMIT = 1  # nolint: privdoc
"""


def test_check_reports_docstrings_of_private_owners(parse: Parse) -> None:
    diags = privdoc.check(parse(_PRIVATE_OWNERS))
    assert diags == [_diag(line) for line in [2, 5, 8, 11]]


def test_check_reports_private_members_of_a_public_class(parse: Parse) -> None:
    assert privdoc.check(parse(_PRIVATE_MEMBERS)) == [_diag(3), _diag(5)]


def test_check_reports_docstrings_nested_in_a_function(parse: Parse) -> None:
    assert privdoc.check(parse(_NESTED)) == [_diag(3), _diag(6)]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_PUBLIC, id="public"),
        pytest.param(_NOT_DOCSTRINGS, id="not-docstrings"),
        pytest.param(_FUNCTION_BODY, id="function-body"),
    ],
)
def test_check_skips_docs_outside_its_scope(parse: Parse, source: str) -> None:
    assert privdoc.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        pytest.param(_COMMENTS, [3, 7, 9, 10], id="above-and-trailing"),
        pytest.param(_DIRECTIVES, [7], id="directives"),
        pytest.param(_HEADER, [5], id="module-header"),
        pytest.param(_DECORATED, [3, 5, 7], id="decorator-gaps"),
        pytest.param(_DECORATED_FIRST, [2], id="decorated-first-statement"),
    ],
)
def test_check_reports_attached_comment_groups(
    parse: Parse, source: str, lines: list[int]
) -> None:
    assert privdoc.check(parse(source)) == [_diag(line) for line in lines]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("_LIMIT = 1", id="assign"),
        pytest.param("_LIMIT: int = 1", id="annotated"),
        pytest.param("type _Alias = int", id="type-alias"),
        pytest.param("_first, _second = 1, 2", id="unpacked"),
    ],
)
def test_check_reports_comments_on_private_bindings(parse: Parse, stmt: str) -> None:
    assert privdoc.check(parse(_binding(stmt))) == [_diag(2)]


@pytest.mark.parametrize(
    "stmt",
    [
        pytest.param("LIMIT = 1", id="public"),
        pytest.param("__all__ = []", id="dunder"),
        pytest.param("first, _second = 1, 2", id="one-public-name"),
        pytest.param("_LIMIT += 1", id="augmented"),
    ],
)
def test_check_skips_comments_on_public_bindings(parse: Parse, stmt: str) -> None:
    assert privdoc.check(parse(_binding(stmt))) == []


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        pytest.param(_NOLINT, [], id="docstring-line"),
        pytest.param(_NOLINT_ON_CLOSING_LINE, [], id="closing-line"),
        pytest.param(_NOLINT_FOR_OTHER_RULE, [2], id="other-rule"),
        pytest.param(_NOLINT_ON_DEF_LINE, [2], id="def-line"),
        pytest.param(_NOLINT_IN_GROUP, [], id="comment-group"),
        pytest.param(_NOLINT_TRAILING, [3], id="other-group"),
    ],
)
def test_check_honors_nolint(parse: Parse, source: str, lines: list[int]) -> None:
    assert privdoc.check(parse(source)) == [_diag(line) for line in lines]


def _binding(stmt: str) -> str:
    return f"import os\n# Note.\n{stmt}\n"


def _diag(line: int) -> Diagnostic:
    message = (
        "comment on identifier outside the exported API; "
        "only the exported API may be documented"
    )
    return Diagnostic("a.py", line, message)
