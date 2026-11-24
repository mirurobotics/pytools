from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder, model, plain

type Parse = Callable[[str], CheckInput]

_POINT: Final = "class Point:\n    x: int\n"
_RUN: Final = "def run(x: int | None) -> list[int]: pass\n"
_MAKE: Final = "def make(): return Point()\n"
_REPORT: Final = 'class "Point" should be directly above its first user'
_LINE_REPORT: Final = 'class "Line" should be directly above its first user "make"'
_PLUGIN_REPORT: Final = 'class "Plugin" should be directly above its first user "Point"'
_STATEMENT_BETWEEN: Final = _POINT + "ORIGIN = 0\n" + _MAKE
_SAME_USER: Final = """\
class Point:
    x: int
class Size:
    width: int
def make(p: Point, s: Size): pass
"""
_DEEPER_ABOVE: Final = """\
class Point:
    x: int
class Line:
    start: Point
def make(line: Line): pass
"""
_DEEPER_BETWEEN: Final = """\
class Point:
    x: int
class Size:
    width: int
class Line:
    size: Size
def make(p: Point, line: Line): pass
"""
_DEEPER_RISES: Final = """\
def make(): return Line()
class Point:
    x: int
class Line:
    start: Point
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
_RISES_PAST_NEED: Final = """\
def make(): return Point()
ORIGIN = 0
class Point:
    x: ORIGIN
"""
_CYCLE: Final = """\
def run(): return A, B
class A:
    other: B
class B:
    other: A
"""
_DATACLASS: Final = "@dataclass(frozen=True)\nclass Point:\n    x: int\n"
_PROTOCOL: Final = """\
class Point(Protocol):
    def x(self) -> int: ...
    def y(self) -> int:
        "Return y."
"""
_PROPERTY: Final = "class Point:\n    @property\n    def x(self): return 0\n"
_BARE_METHOD: Final = "class Point(ABC):\n    @abstractmethod\n    def x(self): pass\n"
_ANNOTATION_ONLY: Final = """\
class Point:
    x: int
def run(): pass
class Other:
    Point: type
    value = Point()
"""
_BRANCH_BINDING: Final = """\
class Point:
    x: int
def run(): pass
class Other:
    if FLAG:
        Point = int
    value = Point()
"""
_WALRUS_BINDING: Final = """\
class Point:
    x: int
def run(): pass
class Other:
    value = False and (Point := int)
    point = Point()
"""
_TYPE_PARAM: Final = """\
class Point:
    x: int
def run(): pass
class Box[Point]:
    value: Point
def make(): return Point()
"""
_NESTED_CLASS_BODY: Final = """\
Point = int
class Box:
    values = [Point for _ in range(3)]
    class Point: pass
    def run(self): pass
    class Other:
        value = Point()
    if FLAG:
        class Third:
            value = Point()
"""
_HOOK_ASSIGNED: Final = """\
def _register(cls): REGISTRY.append(cls)
REGISTRY = []
class Plugin:
    __init_subclass__ = _register
def load(): return Point()
class Point(Plugin): pass
"""
_ITEM_OF_LOCAL: Final = """\
class Settings:
    def __getitem__(self, key): return VALUE
SETTINGS = Settings()
def make(): return Point()
VALUE = 1
def other(): pass
class Point:
    value = SETTINGS["key"]
"""
_NOLINT: Final = "class Point:  # nolint: funcorder\n    x: int\n"
_EXEMPT_BETWEEN: Final = """\
X = 1
class Point:
    x: X
class Other:  # nolint: funcorder
    y: int
def make(): return Point()
"""
_CLASS_BODY: Final = """\
class Box:
    def make(self): return self.Point()
    class Point:
        x: int
"""
_FUNCTION_BODY: Final = """\
def run():
    class Point:
        x: int
    def helper(): pass
    return Point()
"""


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_POINT + _MAKE, id="directly-above"),
        pytest.param(_STATEMENT_BETWEEN, id="statement-between"),
        pytest.param(_SAME_USER, id="another-class-above-the-same-user"),
        pytest.param(_DEEPER_ABOVE, id="class-it-uses-above"),
        pytest.param(_RISES_PAST_NEED, id="move-would-pass-what-it-uses"),
        pytest.param(_USER_STAYS, id="class-user-that-stays"),
        pytest.param("def make(p: 'Point'): pass\n" + _POINT, id="string-annotation"),
        pytest.param(_CYCLE, id="classes-using-each-other"),
        pytest.param(_ITEM_OF_LOCAL, id="definition-indexes-a-local"),
        pytest.param(
            'class Point:\n    print("a")\n' + _RUN + 'print("b")\n' + _MAKE,
            id="class-that-calls-code-past-a-statement",
        ),
        pytest.param(_NOLINT + _RUN + _MAKE, id="nolint"),
    ],
)
def test_plain_violations_skips_placed_class(parse: Parse, source: str) -> None:
    assert plain.plain_violations(_build(parse, source)) == {}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_MAKE + _POINT, {1: f'{_REPORT} "make"'}, id="below-its-user"),
        pytest.param(_POINT + _RUN + _MAKE, {0: f'{_REPORT} "make"'}, id="def-between"),
        pytest.param(
            _POINT + _RUN + "ORIGIN = Point()\n",
            {0: f"{_REPORT} on line 4"},
            id="module-statement",
        ),
        pytest.param(
            _POINT + _RUN + "class Options:\n    Point |= None\n",
            {0: f'{_REPORT} "Options"'},
            id="augmented-assignment",
        ),
        pytest.param(
            _MAKE + _RUN + "class Point:\n    x = dict()\n",
            {2: f'{_REPORT} "make"'},
            id="module-class-that-calls-code",
        ),
        pytest.param(
            _POINT + _RUN + "class Line(Point):\n    def length(self): return 0\n",
            {0: f'{_REPORT} "Line"'},
            id="base",
        ),
        pytest.param(
            _POINT + _RUN + "class Line:\n    def start(self): return Point()\n",
            {0: f'{_REPORT} "Line"'},
            id="method-of-another-class",
        ),
        pytest.param(
            _POINT + _RUN + "def make(p: Point): pass\n",
            {0: f'{_REPORT} "make"'},
            id="annotation",
        ),
        pytest.param(
            _POINT + _RUN + "@register(Point)\ndef make(): pass\n",
            {0: f'{_REPORT} "make"'},
            id="decorator",
        ),
        pytest.param(
            _POINT + _RUN + "def make(p=Point()): pass\n",
            {0: f'{_REPORT} "make"'},
            id="default",
        ),
        pytest.param(
            _DEEPER_BETWEEN, {0: f'{_REPORT} "make"'}, id="deeper-class-between"
        ),
        pytest.param(
            _DEEPER_RISES,
            {1: f'{_REPORT} "Line"', 2: _LINE_REPORT},
            id="deeper-class-rises-with-it",
        ),
        pytest.param(
            _ANNOTATION_ONLY, {0: f'{_REPORT} "Other"'}, id="class-annotation-only"
        ),
        pytest.param(
            _BRANCH_BINDING, {0: f'{_REPORT} "Other"'}, id="class-binding-in-a-branch"
        ),
        pytest.param(
            _WALRUS_BINDING, {0: f'{_REPORT} "Other"'}, id="class-binding-by-walrus"
        ),
        pytest.param(_TYPE_PARAM, {0: f'{_REPORT} "make"'}, id="class-type-param"),
        pytest.param(_HOOK_ASSIGNED, {2: _PLUGIN_REPORT}, id="hook-is-a-bare-def"),
        pytest.param(
            _EXEMPT_BETWEEN, {1: f'{_REPORT} "make"'}, id="exempt-class-between"
        ),
    ],
)
def test_plain_violations_reports_misplaced_class(
    parse: Parse, source: str, expected: dict[int, str]
) -> None:
    assert plain.plain_violations(_build(parse, source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_DATACLASS, id="dataclass"),
        pytest.param("class Point(Enum):\n    X = 1\n", id="enum"),
        pytest.param("class Point(NamedTuple):\n    x: int\n", id="named-tuple"),
        pytest.param("class Point(TypedDict):\n    x: int\n", id="typed-dict"),
        pytest.param(_PROTOCOL, id="protocol-of-stubs"),
        pytest.param(
            "class Point:\n    class Meta:\n        def x(self): return 0\n",
            id="method-of-nested-class",
        ),
    ],
)
def test_plain_violations_places_methodless_class(parse: Parse, source: str) -> None:
    built = _build(parse, source + _RUN + _MAKE)
    assert plain.plain_violations(built) == {0: f'{_REPORT} "make"'}


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("class Point:\n    def __init__(self): pass\n", id="dunder"),
        pytest.param(_PROPERTY, id="property"),
        pytest.param(
            "class Point:\n    if FLAG:\n        def x(self): return 0\n",
            id="method-in-a-branch",
        ),
        pytest.param(_BARE_METHOD, id="pass-body"),
    ],
)
def test_plain_violations_skips_class_with_methods(parse: Parse, source: str) -> None:
    assert plain.plain_violations(_build(parse, source + _RUN + _MAKE)) == {}


def test_check_places_classes_in_each_class_body(parse: Parse) -> None:
    message = 'class "Box.Point" should be directly above its first user "Box.make"'
    assert funcorder.check(parse(_CLASS_BODY)) == [Diagnostic("a.py", 3, message)]


def test_check_skips_loads_hidden_in_class_body(parse: Parse) -> None:
    assert funcorder.check(parse(_NESTED_CLASS_BODY)) == []


def test_check_skips_classes_in_function_bodies(parse: Parse) -> None:
    assert funcorder.check(parse(_FUNCTION_BODY)) == []


def test_plain_violations_follows_a_long_chain(parse: Parse) -> None:
    chain = "".join(map("class C{}(C{}): pass\n".format, range(1, 1200), range(1199)))
    source = "class C0:\n    x: int\n" + _RUN + chain + "def make(): return C1199()\n"
    built = _build(parse, source)
    expected = 'class "C0" should be directly above its first user "C1"'
    assert plain.plain_violations(built) == {0: expected}


def _build(parse: Parse, source: str) -> model.Model:
    file = parse(source)
    return model.build(file, file.tree)
