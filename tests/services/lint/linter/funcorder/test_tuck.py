from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_OBJ: Final = "class Obj:\n    def ident(self): return 1\n"
_BELOW_USER: Final = """\
def test_a(): return [Obj()]
def test_b(): pass
class Obj:
    def ident(self): return 1
"""
_BELOW_HELPERS: Final = """\
def run(): _helper()
def _helper(): return Obj()
def other(): pass
class Obj:
    def ident(self): return 1
"""
_PAST_DECLARATIONS: Final = """\
def run(): return Obj()
class Meta:
    x: int
def other(): pass
class Obj:
    def ident(self): return 1
"""
_LAST_USER: Final = """\
def a(): return Obj()
def x(): pass
def b(): return Obj()
def c(): pass
class Obj:
    def ident(self): return 1
"""
_KEEP_ORDER: Final = """\
def run(): return B(), A()
def other(): pass
class A:
    def a(self): pass
class B:
    def b(self): pass
"""
_CLASS_BODY: Final = """\
class Shape:
    def run(self): return self.Obj()
    def other(self): pass
    class Obj:
        def ident(self): return 1
"""
_TREE_ENDS_BELOW: Final = """\
def run(): _helper(); return Obj()
def other(): pass
class Obj:
    def ident(self): return 1
def _helper(): pass
"""
_STATEMENTS: Final = """\
def run(): return Obj()
A = record("a")
def other(): pass
class Obj:
    def ident(self): _g()
B = record("b")
def _g(): pass
"""
_JUMPED_CALLER: Final = """\
def run(): return Obj()
def other(): _g()
class Obj:
    def ident(self): _g()
def _g(): pass
"""
_CLASS_USER: Final = """\
class Other:
    def use(self): return Obj()
def run(): pass
class Obj:
    def ident(self): return 1
"""
_BASE_NEED: Final = """\
def run(): return Obj()
def other(): pass
class Base:
    x: int
class Obj(Base):
    def ident(self): return 1
"""
_NEED_THROUGH_CALL: Final = """\
def _initialize(): return _helper()
def run(): return Obj()
def other(): return _helper()
def _helper(): return 1
class Obj:
    value = _initialize()
    def ident(self): return 1
"""
_VALUE_THROUGH_CALL: Final = """\
def _initialize(): return VALUE
def run(): return Obj()
VALUE = 1
def other(): pass
class Obj:
    value = _initialize()
    def ident(self): return 1
"""
_HELPER_WAITS: Final = """\
def run(): return Obj()
def other(): pass
C = 1
class Obj:
    def ident(self): return _g()
def _g(x=C): pass
"""
_STATEMENT_NEED: Final = """\
def run(): return Obj()
KEY = "k"
def other(): pass
class Obj:
    key = KEY
    def ident(self): return 1
"""


def _diag(line: int, message: str) -> Diagnostic:
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            _BELOW_USER,
            [_diag(3, '"Obj" should be directly below "test_a"')],
            id="below-its-user",
        ),
        pytest.param(
            _BELOW_HELPERS,
            [_diag(4, '"Obj" should be directly below "_helper"')],
            id="below-its-users-helpers",
        ),
        pytest.param(
            _PAST_DECLARATIONS,
            [_diag(5, '"Obj" should be directly below "run"')],
            id="past-declarations",
        ),
        pytest.param(
            _LAST_USER,
            [_diag(5, '"Obj" should be directly below "b"')],
            id="below-its-last-user",
        ),
        pytest.param(
            _KEEP_ORDER,
            [_diag(3, '"A" should be directly below "run"')],
            id="classes-keep-their-order",
        ),
        pytest.param(
            _CLASS_BODY,
            [_diag(4, '"Shape.Obj" should be directly below "Shape.run"')],
            id="class-body",
        ),
        pytest.param(
            _TREE_ENDS_BELOW,
            [_diag(5, '"_helper" should be directly below "run"')],
            id="user-tree-ends-below-the-class",
        ),
    ],
)
def test_check_reports_class_not_below_its_user(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funcorder.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_OBJ + "def run(): return Obj()\n", id="above-its-user"),
        pytest.param(
            "def run(): return Obj()\n" + _OBJ + "def other(): pass\n",
            id="directly-below-its-user",
        ),
        pytest.param(
            _OBJ + "def other(): pass\ndef new(): return Obj()\n",
            id="used-only-below",
        ),
        pytest.param(_STATEMENTS, id="tree-holds-a-statement"),
        pytest.param(_JUMPED_CALLER, id="would-jump-a-caller-of-its-helper"),
        pytest.param(_CLASS_USER, id="used-only-by-a-class"),
        pytest.param(_BASE_NEED, id="would-rise-past-its-base"),
        pytest.param(_STATEMENT_NEED, id="would-rise-past-a-statement-it-uses"),
        pytest.param(_NEED_THROUGH_CALL, id="would-rise-past-what-its-body-calls"),
        pytest.param(_VALUE_THROUGH_CALL, id="would-rise-past-what-its-calls-read"),
        pytest.param(_HELPER_WAITS, id="would-take-a-helper-past-its-default"),
    ],
)
def test_check_skips_class_left_where_it_is(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []
