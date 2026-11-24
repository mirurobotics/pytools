from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder, model, order

type Parse = Callable[[str], CheckInput]

_CALL_ORDER: Final = """\
def generate(): _validate_args(); return _checksum()
def verify(): return _checksum() == 0
def _validate_args(): _validate_prefix(); _validate_size()
def _validate_prefix(): pass
def _validate_size(): pass
def _checksum(): return 0
"""
_CARRIED: Final = """\
def run(): _f()
def _g(): pass
C: Final = 1
def _f(): pass
"""
_DEFAULT_FROM_STATEMENT: Final = """\
def root(): _helper()
C = 1
def _helper(): pass
def other(x=C): _helper()
"""
_DEFAULT_BELOW_CALLER: Final = """\
def run(): other()
C = 1
def _x(): pass
def other(x=C): pass
"""
_EXEMPT_CYCLE_MEMBER: Final = """\
def _e(): _a()  # nolint: funcorder
def run(): pass
def _a(): _b()
def _b(): _a(); _e()
def _c(): pass
"""
_HEADER: Final = """\
import os
X: Final = 1
def _helper(): pass
def run(): _helper()
"""
_STATEMENT_ORDER: Final = """\
def _f(): pass
A = record("a")
def _g(): pass
B = record("b")
def _h(): pass
def run(): _h(); _g()
"""
_CLASS_NEEDS: Final = """\
def run(): _f(); _make()
def _make(): return 1
class P:
    x = _make()
def _f(p: P): pass
"""
_CLASS_STAYS: Final = """\
def main(): _a(); _b()
def _a(): return Point()
def _b(): pass
X = 1
class Point:
    x = X
"""
_DEFAULT_FROM_CLASS_THAT_STAYS: Final = """\
def make(): _d(); return F()
X = 1
class F:
    y = X
def _d(p=F()): pass
"""
_WAITS_WHERE_CLASS_GOES: Final = """\
def main(): _b(); _a()
def _a(): return P()
class P:
    x: int
def _b(p=P()): pass
"""
_CARRIED_PAST_CLASS: Final = """\
def main(): _a(); _b()
def _a(): pass
X = 1
class P:
    x: int
def _b(p=P()): pass
"""
_CLASS_CHAIN_NEEDS: Final = """\
def run(): _f(); _make()
def _make(): return 1
class Q:
    x = _make()
class P(Q): pass
def _f(p: P): pass
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            _CALL_ORDER,
            [
                Diagnostic(
                    "a.py", 3, '"_validate_args" should be directly below "generate"'
                ),
                Diagnostic("a.py", 6, '"_checksum" should be directly below "verify"'),
            ],
            id="helpers-follow-call-order",
        ),
        pytest.param(
            _CARRIED,
            [Diagnostic("a.py", 4, '"_f" should be directly below "run"')],
            id="statement-moves-with-def-below-it",
        ),
        pytest.param(
            "def _b(): _a()\ndef run(): _a()\ndef _a(): _b()\n",
            [Diagnostic("a.py", 1, '"_b" should be directly below "_a"')],
            id="cycle-member-follows-its-caller",
        ),
    ],
)
def test_check_reports_def_not_directly_below(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funcorder.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "def run(): _f()\nC: Final = 1\ndef _f(): pass\n",
            id="statement-between-caller-and-callee",
        ),
        pytest.param(
            "def _b(): _a()\ndef _a(): _b()\ndef run(): pass\n", id="cycle-opener"
        ),
        pytest.param(_EXEMPT_CYCLE_MEMBER, id="exempt-member-leaves-cycle-open"),
    ],
)
def test_check_skips_def_directly_below(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_HEADER, ([0, 1, 3, 2], {2}), id="header-stays"),
        pytest.param(_CARRIED, ([0, 2, 3, 1], {2, 3}), id="statement-moves-with-def"),
        pytest.param(
            _STATEMENT_ORDER,
            ([1, 3, 5, 4, 2, 0], {2, 4}),
            id="statements-keep-their-order",
        ),
        pytest.param(
            _DEFAULT_FROM_STATEMENT,
            ([0, 1, 3, 2], {2}),
            id="statement-a-later-def-uses-stays",
        ),
        pytest.param(
            _DEFAULT_BELOW_CALLER, ([0, 1, 2, 3], set()), id="def-waits-for-its-default"
        ),
        pytest.param(
            _CLASS_NEEDS, ([0, 1, 3], {1, 3}), id="user-waits-for-class-needs"
        ),
        pytest.param(
            _CLASS_CHAIN_NEEDS,
            ([0, 1, 4], {1, 4}),
            id="user-waits-for-class-chain-needs",
        ),
        pytest.param(
            _CLASS_STAYS, ([0, 1, 2, 3, 4], {1, 2}), id="user-skips-class-that-stays"
        ),
        pytest.param(
            _DEFAULT_FROM_CLASS_THAT_STAYS,
            ([0, 1, 2, 3], set()),
            id="def-waits-for-class-that-stays",
        ),
        pytest.param(
            _WAITS_WHERE_CLASS_GOES,
            ([0, 1, 3], {1, 3}),
            id="def-waits-for-where-its-class-goes",
        ),
        pytest.param(
            _CARRIED_PAST_CLASS,
            ([0, 1, 2, 4], {1, 2, 4}),
            id="statement-carried-past-class-that-moves",
        ),
    ],
)
def test_arrange_orders_the_scope(
    parse: Parse, source: str, expected: tuple[list[int], set[int]]
) -> None:
    file = parse(source)
    assert order.arrange(model.build(file, file.tree)) == expected
