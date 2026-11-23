from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.nestdepth import nestdepth

Parse = Callable[[str], CheckInput]

_TWO_LEVELS = """\
def f():
    if a:
        if b:
            pass
"""
_OVER_LIMIT_SIBLINGS = """\
def f():
    if a:
        for b in c:
            if d:
                pass
        while e:
            pass
"""
_NESTED_FUNCTION = """\
def outer():
    if a:
        def inner():
            if b:
                if c:
                    pass
"""
_MODULE_LEVEL = """\
if a:
    if b:
        if c:
            pass
"""
_FOR = """\
def f():
    for a in b:
        if c:
            pass
"""
_ASYNC_FOR = """\
async def f():
    async for a in b:
        if c:
            pass
"""
_WHILE = """\
def f():
    while a:
        if b:
            pass
"""
_WITH = """\
def f():
    with a:
        if b:
            pass
"""
_ASYNC_WITH = """\
async def f():
    async with a:
        if b:
            pass
"""
_TRY = """\
def f():
    try:
        if a:
            pass
    finally:
        pass
"""
_TRY_STAR = """\
def f():
    try:
        if a:
            pass
    except* E:
        pass
"""
_MATCH = """\
def f():
    match a:
        case _:
            if b:
                pass
"""
_IF_ELSE = """\
def f():
    if a:
        if b:
            pass
    else:
        if c:
            pass
"""
_FOR_ELSE = """\
def f():
    for a in b:
        if c:
            pass
    else:
        if d:
            pass
"""
_WHILE_ELSE = """\
def f():
    while a:
        if b:
            pass
    else:
        if c:
            pass
"""
_TRY_CLAUSES = """\
def f():
    try:
        if a:
            pass
    except E:
        if b:
            pass
    else:
        if c:
            pass
    finally:
        if d:
            pass
"""
_MATCH_CASES = """\
def f():
    match a:
        case 1:
            if b:
                pass
        case _:
            if c:
                pass
"""
_ELIF = """\
def f():
    if a:
        pass
    elif b:
        if c:
            pass
    else:
        if d:
            pass
"""
_IF_IN_ELSE = """\
def f():
    if a:
        pass
    else:
        if b:
            pass
"""
_MESSAGE = (
    "nesting depth is 2 (limit 1) — consider early returns or extracting a helper"
)


def _diags(lines: list[int]) -> list[Diagnostic]:
    return [Diagnostic("a.py", line, _MESSAGE) for line in lines]


@pytest.mark.parametrize(
    ("max_depth", "lines"),
    [
        pytest.param(3, [], id="under"),
        pytest.param(2, [], id="at"),
        pytest.param(1, [3], id="over"),
    ],
)
def test_check_reports_statements_over_the_limit(
    parse: Parse, max_depth: int, lines: list[int]
) -> None:
    assert nestdepth.check(parse(_TWO_LEVELS), max_depth) == _diags(lines)


def test_check_reports_each_over_limit_statement_once(parse: Parse) -> None:
    assert nestdepth.check(parse(_OVER_LIMIT_SIBLINGS), 1) == _diags([3, 6])


def test_check_restarts_depth_in_nested_function(parse: Parse) -> None:
    assert nestdepth.check(parse(_NESTED_FUNCTION), 1) == _diags([5])


def test_check_ignores_code_outside_functions(parse: Parse) -> None:
    assert nestdepth.check(parse(_MODULE_LEVEL), 1) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param(_TWO_LEVELS, 3, id="if"),
        pytest.param(_FOR, 3, id="for"),
        pytest.param(_ASYNC_FOR, 3, id="async-for"),
        pytest.param(_WHILE, 3, id="while"),
        pytest.param(_WITH, 3, id="with"),
        pytest.param(_ASYNC_WITH, 3, id="async-with"),
        pytest.param(_TRY, 3, id="try"),
        pytest.param(_TRY_STAR, 3, id="try-star"),
        pytest.param(_MATCH, 4, id="match"),
    ],
)
def test_check_counts_a_level_per_block_statement(
    parse: Parse, source: str, line: int
) -> None:
    assert nestdepth.check(parse(source), 1) == _diags([line])


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        pytest.param(_IF_ELSE, [3, 6], id="if-else"),
        pytest.param(_FOR_ELSE, [3, 6], id="for-else"),
        pytest.param(_WHILE_ELSE, [3, 6], id="while-else"),
        pytest.param(_TRY_CLAUSES, [3, 6, 9, 12], id="try-except-else-finally"),
        pytest.param(_MATCH_CASES, [4, 7], id="match-cases"),
    ],
)
def test_check_counts_clauses_at_their_statement_depth(
    parse: Parse, source: str, lines: list[int]
) -> None:
    assert nestdepth.check(parse(source), 1) == _diags(lines)


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        pytest.param(_ELIF, [5, 8], id="elif"),
        pytest.param(_IF_IN_ELSE, [5], id="if-in-else"),
    ],
)
def test_check_tells_elif_from_if_in_else(
    parse: Parse, source: str, lines: list[int]
) -> None:
    assert nestdepth.check(parse(source), 1) == _diags(lines)
