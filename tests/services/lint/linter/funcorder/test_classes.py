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
@dec
def k(): pass
class R:
    r = k
def u(): pass
u = 1
class S:
    s = u
@dec([j])
class T: pass
class W:
    global gx
    gx = 2
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
_GLOBAL_IN_DEF: Final = """\
def setup(): global X; X = 2
class Point:
    x: X
setup()
def make(): return Point()
"""
_GLOBAL_IN_CLASS: Final = """\
class Point: pass
def run(): pass
class Other:
    global Point; Point = int
def make(): return Point()
"""
_GLOBAL_WRITTEN_BELOW: Final = """\
X = 1
class Point:
    x: X
class Other:
    global X
    X = 2
def make(): return Point()
"""
_GLOBAL_CALLED: Final = """\
def setup(): global make; make = int
setup()
def run(): return Point()
class Point:
    x = make()
"""
_GLOBAL_HOOK: Final = """\
def _hook(owner, name): pass
def install(): global _hook; _hook = Hook()
install()
def make(): return Point()
def helper(): pass
class Point:
    x = _hook
"""
_TYPE_PARAM_IN_METHOD: Final = """\
class Item: pass
def run(): pass
class Box[Item]:
    def method(self): return Item
def make(): return Item()
"""
_TYPE_PARAM_IN_DECORATOR: Final = """\
class Item: pass
@register(lambda: Item)
class Box[Item]: pass
def make(): return Item()
"""
_TYPE_PARAM_IN_NESTED_METHOD: Final = """\
class Item: pass
def make():
    class Box[Item]:
        def method(self): return Item
def last(): return Item()
"""
_TYPE_PARAM_IN_NESTED_BASES: Final = """\
class Item: pass
def make():
    class Box[Item](list[Item]): pass
def last(): return Item()
"""
_TYPE_PARAM_IN_ANNOTATION: Final = """\
class Item: pass
def make():
    def inner[Item](arg: Item): pass
def last(): return Item()
"""
_LAMBDA_DEFAULT: Final = """\
class Point: pass
def run(): pass
def factory(make=lambda: Point): return make()
def last(): return Point()
"""
_LAMBDA_IN_COMPREHENSION: Final = """\
class Point: pass
def run(): pass
makers = [lambda: Point for Point in (int,)]
def last(): return Point()
"""
_TYPE_PARAM_IN_DEFAULT: Final = """\
class Item: pass
def make():
    def inner[Item](arg=Item): pass
def last(): return Item()
"""
_LAMBDA_IN_FIRST_ITERABLE: Final = """\
class Point: pass
def run(): pass
points = [Point for Point in map(lambda raw: Point(raw), RAW)]
def last(): return Point()
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
    expected = {3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 17, 18, 20, 23, 24, 25}
    assert _kept(parse, _RUNS_CODE) == expected


def test_find_classes_keeps_rebound_classes(parse: Parse) -> None:
    assert _kept(parse, _REBOUND) == {0, 2}
    assert not _find(parse, _REBOUND).uses


def _kept(parse: Parse, source: str) -> set[int]:
    count = len(parse(source).tree.body)
    classes = _find(parse, source)
    return {idx for idx in range(count) if not classes.may_pass([idx], [])}


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_DELETED_BELOW, id="move-would-pass-a-deletion"),
        pytest.param(_REASSIGNED_BELOW, id="move-would-pass-an-assignment"),
        pytest.param(_REDEFINED_BELOW, id="move-would-pass-a-def-it-reads"),
        pytest.param(_SET_THROUGH_CALL, id="move-would-pass-a-call"),
        pytest.param(_GLOBAL_IN_DEF, id="def-may-bind-what-it-reads"),
        pytest.param(_GLOBAL_IN_CLASS, id="class-body-rebinds-its-name"),
        pytest.param(_GLOBAL_WRITTEN_BELOW, id="move-would-pass-a-global-write"),
        pytest.param(_GLOBAL_CALLED, id="class-calls-a-global-set-in-a-def"),
        pytest.param(_GLOBAL_HOOK, id="class-stores-a-def-made-global"),
    ],
)
def test_find_classes_leaves_class_in_place(parse: Parse, source: str) -> None:
    assert _find(parse, source).uses == {}


@pytest.mark.parametrize(
    ("source", "user"),
    [
        pytest.param(_TYPE_PARAM_IN_METHOD, 3, id="class-in-scope"),
        pytest.param(_TYPE_PARAM_IN_DECORATOR, 1, id="decorator-outside-them"),
        pytest.param(_TYPE_PARAM_IN_NESTED_METHOD, 2, id="class-in-a-def"),
        pytest.param(_TYPE_PARAM_IN_NESTED_BASES, 2, id="bases-in-a-def"),
        pytest.param(_TYPE_PARAM_IN_ANNOTATION, 2, id="annotation-in-a-def"),
        pytest.param(_TYPE_PARAM_IN_DEFAULT, 1, id="default-in-a-def"),
    ],
)
def test_find_classes_scopes_type_params(parse: Parse, source: str, user: int) -> None:
    assert _find(parse, source).uses[0].user == user


@pytest.mark.parametrize(
    ("source", "user"),
    [
        pytest.param(_LAMBDA_DEFAULT, 2, id="lambda-in-a-default"),
        pytest.param(_LAMBDA_IN_COMPREHENSION, 3, id="lambda-in-a-comprehension"),
        pytest.param(_LAMBDA_IN_FIRST_ITERABLE, 2, id="lambda-in-a-first-iterable"),
    ],
)
def test_find_classes_finds_users_in_lambdas(
    parse: Parse, source: str, user: int
) -> None:
    assert _find(parse, source).uses[0].user == user


def test_find_classes_places_users_that_stay(parse: Parse) -> None:
    assert _find(parse, _USER_STAYS).uses == {2: Use(3, 3, 0)}


def _find(parse: Parse, source: str) -> Classes:
    file = parse(source)
    return model.build(file, file.tree).classes
