from collections.abc import Callable
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.classes import Classes, Use

type Parse = Callable[[str], CheckInput]

_CLASS_CHAIN: Final = """\
C = 1
class Q:
    x = C
class P:
    q: Q
def run(p: P): pass
"""
_RUNS_CODE: Final = """\
from m import dec
V = 1
class A:
    a: Opt[V] = field(default=V)
    b = [V, (V,)]
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
    assert _find(parse, _RUNS_CODE).runs == {3, 4, 5, 6, 7, 8, 9}


def test_find_classes_places_users_that_stay(parse: Parse) -> None:
    assert _find(parse, _USER_STAYS).uses == {2: Use(3, 3, 0)}


def _find(parse: Parse, source: str) -> Classes:
    file = parse(source)
    return model.build(file, file.tree).classes
