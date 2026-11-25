from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.docrestate import docrestate

type Parse = Callable[[str], CheckInput]

_ONE_LINE: Final = """\
def run():
    '''Run runs.'''
"""
_MULTI_LINE: Final = """\
def run():
    '''Run.

    Runs the run.
    '''
"""
_OWNERS: Final = """\
class Client:
    '''A client.'''

    def close(self):
        '''Close it.'''

        class Inner:
            '''The inner class.'''

async def run():
    '''Run.'''

    def helper():
        '''Return the helper.'''
"""
_NOT_DOCSTRINGS: Final = """\
'''Run runs.'''

def run():
    x = 1
    '''Run runs.'''

def stop():
    f'''Stop stops.'''

def load():
    b'''Load loads.'''

class Client:
    name = '''A client.'''
"""
_NOLINT: Final = """\
def run():
    '''Run runs.'''  # nolint: docrestate
"""
_NOLINT_ON_CLOSING_LINE: Final = """\
def run():
    '''Run.
    Runs.
    '''  # nolint: docrestate
"""
_NOLINT_FOR_OTHER_RULE: Final = """\
def run():
    '''Run runs.'''  # nolint: funclen
"""
_NOLINT_ON_DEF_LINE: Final = """\
def run():  # nolint: docrestate
    '''Run runs.'''
"""
_PARENTHESIZED: Final = """\
def run():
    (
        '''Run runs.'''
    )
"""


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_ONE_LINE, id="one-line"),
        pytest.param(_MULTI_LINE, id="multi-line"),
    ],
)
def test_check_reports_a_restating_docstring(parse: Parse, source: str) -> None:
    assert docrestate.check(parse(source)) == [_diag(2, "run")]


def test_check_reports_every_owner_in_line_order(parse: Parse) -> None:
    diags = docrestate.check(parse(_OWNERS))
    owners = [(2, "Client"), (5, "close"), (8, "Inner"), (11, "run"), (14, "helper")]
    assert diags == [_diag(line, name) for line, name in owners]


def test_check_skips_strings_that_are_not_docstrings(parse: Parse) -> None:
    assert docrestate.check(parse(_NOT_DOCSTRINGS)) == []


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        pytest.param(_NOLINT, [], id="docstring-line"),
        pytest.param(_NOLINT_ON_CLOSING_LINE, [], id="closing-line"),
        pytest.param(_NOLINT_FOR_OTHER_RULE, [2], id="other-rule"),
        pytest.param(_NOLINT_ON_DEF_LINE, [2], id="def-line"),
    ],
)
def test_check_honors_nolint(parse: Parse, source: str, lines: list[int]) -> None:
    assert docrestate.check(parse(source)) == [_diag(line, "run") for line in lines]


def test_check_reports_parenthesized_docstring(parse: Parse) -> None:
    assert docrestate.check(parse(_PARENTHESIZED)) == [_diag(3, "run")]


@pytest.mark.parametrize(
    ("name", "doc"),
    [
        pytest.param("run", "Run starts the pool and blocks until done.", id="more"),
        pytest.param("to_json", "Return the value.", id="only-filler"),
    ],
)
def test_check_skips_docstrings_that_say_more(
    parse: Parse, name: str, doc: str
) -> None:
    assert docrestate.check(parse(_source(name, doc))) == []


@pytest.mark.parametrize(
    ("name", "doc"),
    [
        pytest.param("new_client", "Create a new client.", id="constructor"),
        pytest.param("get_user_id", "Get the user ID.", id="getter"),
        pytest.param("user_ids", "Return the user IDs.", id="plural"),
        pytest.param("ClientConfig", "ClientConfig is a ClientConfig.", id="whole"),
        pytest.param("NewClient", "New client.", id="camel"),
        pytest.param("Base64Encode", "Base 64 encode.", id="digits"),
        pytest.param("HTTPServer", "HTTP server.", id="acronym"),
        pytest.param("GetUserID", "Get user ID.", id="trailing-acronym"),
        pytest.param("UserIDs", "User IDs.", id="plural-acronym"),
        pytest.param("URLs", "The URLs.", id="only-plural-acronym"),
        pytest.param("IDsFor", "IDs for.", id="leading-plural-acronym"),
        pytest.param("CPUUsage", "CPU usage.", id="acronym-before-capital"),
    ],
)
def test_check_splits_names_into_words(parse: Parse, name: str, doc: str) -> None:
    assert docrestate.check(parse(_source(name, doc))) == [_diag(2, name)]


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param('Run is "/".', id="double-quote"),
        pytest.param('Run is "run".', id="double-quoted-word"),
        pytest.param("Run is `run`.", id="backtick"),
        pytest.param("Run is 'run'.", id="single-quote"),
        pytest.param("Run is ('run').", id="parenthesized-quote"),
        pytest.param("Run is 'the run'.", id="quoted-words"),
        pytest.param("Run returns +.", id="plus"),
        pytest.param("Run is - the run.", id="dash"),
        pytest.param("Run is {'a'}.", id="set"),
        pytest.param("Run returns [].", id="brackets"),
        pytest.param("Run is (.", id="paren"),
    ],
)
def test_check_reads_quotes_and_symbols_as_meaning(parse: Parse, doc: str) -> None:
    assert docrestate.check(parse(_source("run", doc))) == []


def test_check_reads_an_unclosed_quote_as_a_word(parse: Parse) -> None:
    source = _source("run", "Run is 'run.")
    assert docrestate.check(parse(source)) == [_diag(2, "run")]


@pytest.mark.parametrize(
    ("name", "doc"),
    [
        pytest.param("run", "Runs.", id="runs"),
        pytest.param("close", "Closes.", id="closes"),
        pytest.param("close", "Closing.", id="closing"),
        pytest.param("parse", "Parsed.", id="parsed"),
        pytest.param("load", "Loading.", id="loading"),
        pytest.param("load", "Loaded.", id="loaded"),
        pytest.param("entry", "Entries.", id="entries"),
        pytest.param("copy", "Copied.", id="copied"),
        pytest.param("match", "Matches.", id="matches"),
        pytest.param("box", "Boxes.", id="boxes"),
        pytest.param("use", "Used.", id="used"),
        pytest.param("settings", "Return the setting.", id="singular"),
    ],
)
def test_check_matches_inflected_name_words(parse: Parse, name: str, doc: str) -> None:
    assert docrestate.check(parse(_source(name, doc))) == [_diag(2, name)]


@pytest.mark.parametrize(
    ("name", "doc"),
    [
        pytest.param("Str", "Str returns the string.", id="short-stem-ing"),
        pytest.param("string", "Str.", id="prefix"),
        pytest.param("car", "Card.", id="d-without-e"),
        pytest.param("y", "Yes.", id="es-without-sibilant"),
        pytest.param("use", "User.", id="other-suffix"),
        pytest.param("configuration", "Config.", id="abbreviation"),
    ],
)
def test_check_skips_other_word_forms(parse: Parse, name: str, doc: str) -> None:
    assert docrestate.check(parse(_source(name, doc))) == []


def _source(name: str, doc: str) -> str:
    return f"def {name}():\n    '''{doc}'''\n"


def _diag(line: int, name: str) -> Diagnostic:
    message = (
        f"docstring for {name} only restates its name; "
        "say what it does or remove it"
    )
    return Diagnostic("a.py", line, message)
