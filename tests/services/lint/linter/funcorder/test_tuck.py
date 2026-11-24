from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_OBJ: Final = "class Obj:\n    def ident(self): return 1\n"
_BELOW_USER: Final = "def test_a(): return [Obj()]\ndef test_b(): pass\n" + _OBJ
_BELOW_HELPERS: Final = (
    "def run(): _helper()\ndef _helper(): return Obj()\ndef other(): pass\n" + _OBJ
)
_PAST_DECLARATIONS: Final = (
    "def run(): return Obj()\nclass Meta:\n    x: int\ndef other(): pass\n" + _OBJ
)
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
_SETTER: Final = """\
def run(): return Obj()
def other(): pass
class Obj:
    @property
    def size(self): return 1
    @size.setter
    def size(self, value): pass
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
_JUMPED_CALLER: Final = (
    "def run(): return Obj()\ndef other(): _g()\nclass Obj:\n"
    + "    def ident(self): _g()\ndef _g(): pass\n"
)
_CLASS_USER: Final = (
    "class Other:\n    def use(self): return Obj()\ndef run(): pass\n" + _OBJ
)
_BASE_NEED: Final = (
    "def run(): return Obj()\ndef other(): pass\nclass Base:\n    x: int\n"
    + "class Obj(Base):\n    def ident(self): return 1\n"
)
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
_OWN_DEF_CALLED: Final = """\
def run(): return Obj()
VALUE = 1
def other(): pass
class Obj:
    def _compute(): return VALUE
    x = _compute()
    def ident(self): return 1
"""
_DECORATED_HELPER: Final = """\
def _register(fn): REGISTRY.append(fn); return fn
def run(): return Obj()
REGISTRY = []
def other(): pass
class Obj:
    def ident(self): return _g()
@_register
def _g(): pass
"""
_GLOBAL_THROUGH_CALL: Final = """\
X = 1
def configure(): global X; X = 2
def run(): return Obj()
configure()
def other(): pass
class Obj:
    x: X
    def ident(self): return 1
"""
_NONLOCAL: Final = """\
def outer():
    value = 1
    class Box:
        def make(self): return self.Obj()
        class Update:
            nonlocal value
            value = 2
        def other(self): pass
        class Obj:
"""
_NONLOCAL_WRITE: Final = (
    _NONLOCAL + "            captured = value\n            def ident(self): return 1\n"
)
_NONLOCAL_DEFAULT: Final = (
    _NONLOCAL + "            def ident(self, v=value): return v\n"
)
_BOX: Final = "class Box:\n    def make(self): return self.Obj()\n"
_UPDATE: Final = "    class Update:\n        STATE.value = 2\n"
_CARRY: Final = "def other(): pass\nclass Obj:\n    def ident(self): return helper()\n"
_CARRIED_DEFAULT: Final = (
    "import sys\ndef make(): return Obj()\nsys.state = 2\n"
    + _CARRY
    + "def helper(value=sys.state): return value\n"
)
_CARRIED_HINT: Final = (
    "VALUE = 1\ndef make(): return Obj()\n"
    + "class Update:\n    global VALUE\n    VALUE = 2\n"
    + _CARRY
    + "def helper(x: VALUE = 0): return x\n"
)
_CARRIED_OVERLOAD: Final = (
    'def make(): return Obj()\nprint("a")\n'
    + _CARRY
    + '@overload\ndef helper(x=print("b")): ...\ndef helper(x=0): return x\n'
)
_STUB_RUNS_CODE: Final = (
    "def make(): return C()\nX = 1\ndef run(): return Obj()\nclass C:\n    y: X\n"
    + "class Obj:\n    def m(self): return helper()\n"
    + "@overload\ndef helper(x=make()): ...\ndef helper(x=0): return x\n"
)
_STAR_IMPORT: Final = (
    "def run(): return Obj()\nfrom m import *\ndef other(): pass\n" + _OBJ
)
_HELPER_WAITS: Final = (
    "def run(): return Obj()\ndef other(): pass\nC = 1\nclass Obj:\n"
    + "    def ident(self): return _g()\ndef _g(x=C): pass\n"
)
_STATEMENT_NEED: Final = (
    'def run(): return Obj()\nKEY = "k"\ndef other(): pass\n'
    + "class Obj:\n    key = KEY\n    def ident(self): return 1\n"
)


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
        pytest.param(
            _SETTER,
            [_diag(3, '"Obj" should be directly below "run"')],
            id="class-with-a-property-setter",
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
        pytest.param(_OWN_DEF_CALLED, id="definition-calls-its-own-def"),
        pytest.param(_DECORATED_HELPER, id="tree-holds-a-decorated-def"),
        pytest.param(_HELPER_WAITS, id="would-take-a-helper-past-its-default"),
        pytest.param(_CARRIED_DEFAULT, id="would-take-a-helper-past-a-write"),
        pytest.param(_CARRIED_HINT, id="would-take-a-helper-past-its-hint"),
        pytest.param(_CARRIED_OVERLOAD, id="would-take-an-overload-past-a-call"),
        pytest.param(_STUB_RUNS_CODE, id="tree-holds-a-stub-that-calls-code"),
        pytest.param(_GLOBAL_THROUGH_CALL, id="would-rise-past-a-call"),
        pytest.param(_STAR_IMPORT, id="would-rise-past-a-star-import"),
        pytest.param(_NONLOCAL_WRITE, id="would-rise-past-a-nonlocal-write"),
        pytest.param(_NONLOCAL_DEFAULT, id="default-would-pass-a-nonlocal-write"),
    ],
)
def test_check_skips_class_left_where_it_is(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []


@pytest.mark.parametrize(
    "writer",
    [
        pytest.param(_UPDATE, id="class"),
        pytest.param("    @_bump\n    def other(self): pass\n", id="decorated-def"),
    ],
)
@pytest.mark.parametrize(
    "header",
    [
        pytest.param("    @_register\n    class Obj:\n", id="decorator"),
        pytest.param("    class Obj(Base):\n", id="base"),
        pytest.param("    class Obj:\n        x = _initialize()\n", id="call"),
        pytest.param("    class Obj:\n        x = SETTINGS['key']\n", id="subscript"),
        pytest.param("    class Obj:\n        x = STATE.value\n", id="attribute"),
        pytest.param("    class Obj:\n        x = OTHER + 1\n", id="operator"),
        pytest.param("    class Obj:\n        def go(self, v: f()): pass\n", id="hint"),
        pytest.param("    class Obj:\n        def go(self, v: A.b): pass\n", id="dot"),
        pytest.param("    class Obj:\n        x: 1 = 1 + 1\n", id="annotated-value"),
        pytest.param("    class Obj(metaclass=1):\n", id="keyword"),
        pytest.param("    class Obj:\n        (1).b = 1\n", id="attribute-target"),
        pytest.param(
            "    class Obj:\n        def go(self, v=1 + 1): pass\n", id="default"
        ),
        pytest.param("    class Obj:\n        x: Alias = 1\n", id="annotation-name"),
    ],
)
def test_check_skips_nested_class_running_code(
    parse: Parse, writer: str, header: str
) -> None:
    source = _BOX + writer + header + "        def ident(self): return 1\n"
    assert funcorder.check(parse(source)) == []


def test_check_tucks_inert_nested_class(parse: Parse) -> None:
    inert = "    class Obj:\n        x = 1\n        def ident(self): pass\n"
    message = '"Box.Obj" should be directly below "Box.make"'
    assert funcorder.check(parse(_BOX + _UPDATE + inert)) == [_diag(5, message)]
