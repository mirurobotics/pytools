from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.classes import Classes, Use

type Parse = Callable[[str], CheckInput]

_CLASS_CHAIN: Final = """\
C = 1
class Q:
    x: C
class P:
    q: Q
def run(p: P): pass
"""
_RUNS_CODE: Final = """\
from m import dec
V = 1
class A:
    a: Opt[V]
    b: Callable[[V], tuple[V]]
class B(V): pass
class C:
    c = V.x
class D:
    d = V + 1
class E:
    e = V["k"]
class F:
    f = sorted(items, key=lambda n: V)
@V
class G: pass
class H:
    def _c(): pass
    h = _c()
@dec
class I:
    i = dec(V)
def j(p: V = V) -> V: pass
class K:
    k = sorted(items, key=j)
class L:
    lo, hi = V
class M:
    m = V
class N:
    n: int = V
class O:
    o = j
class P:
    for x in (V,): pass
class Q:
    def m(self, p=V): return p
"""
_REBOUND: Final = """\
class Point:
    x = 1
def old(p=Point): pass
class Point:
    x = 2
def new(p=Point): pass
"""
_DELETED_BELOW: Final = """\
VALUE = 1
class Point:
    x: VALUE
del VALUE
def run(): pass
def make(): return Point()
"""
_REASSIGNED_BELOW: Final = """\
VALUE = 1
class Point:
    x: VALUE
VALUE = 2
def run(): pass
def make(): return Point()
"""
_REDEFINED_BELOW: Final = """\
VALUE = 1
class Point:
    x: VALUE
def VALUE(): pass
def make(): return Point()
"""
_SET_THROUGH_CALL: Final = """\
X = 1
def configure(): global X; X = 2
class Point:
    x: X
configure()
def run(): pass
def make(): return Point()
"""
_USER_STAYS: Final = """\
def make(): return Line()
X = 1
class Point:
    x: int
class Line:
    start: Point
    y = X
"""


def test_find_classes_chains_methodless_class_needs(parse: Parse) -> None:
    inherited = _find(parse, _CLASS_CHAIN).inherited
    assert inherited == {2: frozenset({0}), 3: frozenset({0, 1})}


def test_find_classes_finds_decls_that_run_code(parse: Parse) -> None:
    expected = {3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 17, 18}
    assert _find(parse, _RUNS_CODE).kept == expected


def test_find_classes_keeps_rebound_classes(parse: Parse) -> None:
    classes = _find(parse, _REBOUND)
    assert (classes.kept, classes.uses) == ({0, 2}, {})


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_DELETED_BELOW, id="move-would-pass-a-deletion"),
        pytest.param(_REASSIGNED_BELOW, id="move-would-pass-an-assignment"),
        pytest.param(_REDEFINED_BELOW, id="move-would-pass-a-def-it-reads"),
        pytest.param(_SET_THROUGH_CALL, id="move-would-pass-a-call"),
    ],
)
def test_find_classes_leaves_class_in_place(parse: Parse, source: str) -> None:
    assert _find(parse, source).uses == {}


def test_find_classes_places_users_that_stay(parse: Parse) -> None:
    assert _find(parse, _USER_STAYS).uses == {2: Use(3, 3, 0)}


def _find(parse: Parse, source: str) -> Classes:
    file = parse(source)
    return model.build(file, file.tree).classes
