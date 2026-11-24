import ast
from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import refs

type Parse = Callable[[str], CheckInput]

_NESTED_DEF: Final = """\
def run():
    def inner(): return helper()
    return inner
"""
_NESTED_DEF_OUTER_PARTS: Final = """\
def run():
    @deco
    def inner(x=make()): pass
"""
_COMPREHENSION_THEN_CALL: Final = """\
def run(items):
    names = [helper for helper in items]
    return helper()
"""
_CLASS_BODY_IN_DEF: Final = """\
def run():
    class C:
        x = 1
        def m(self): return x()
    return C
"""
_GLOBAL: Final = """\
def run():
    global helper
    helper = cache(helper)
    return helper()
"""
_CLASS: Final = """\
class T:
    X = setup()
    def run(self): return helper()
"""
_SHADOWING_NESTED_DEF: Final = """\
def run():
    def value(): pass
    return value()
"""
_EXCEPT_ALIAS: Final = """\
def run():
    try:
        pass
    except ValueError as value:
        return value
"""
_COMPREHENSION_WALRUS: Final = """\
def run(items):
    results = [(helper := item) for item in items]
    return helper()
"""
_NONLOCAL: Final = """\
def run():
    helper = 1
    def inner():
        nonlocal helper
        helper = 2
    return helper
"""
_DOTTED_IMPORT: Final = """\
def run():
    import os.path
    return os.path.join()
"""
_LOCAL_IMPORT: Final = """\
def run(value):
    from json import loads
    return loads(value)
"""
_IMPORT_ALIAS: Final = """\
def run(value):
    import json as j
    return j.loads(value)
"""
_MATCH_CAPTURE: Final = """\
def run(item):
    match item:
        case [value]:
            return value
"""
_CLASSMETHOD: Final = """\
class T:
    @classmethod
    def make(cls): return cls.build()
"""
_STATICMETHOD: Final = """\
class T:
    @staticmethod
    def run(item): item.help()
"""
_NESTED_CLASS: Final = """\
class T:
    class Inner:
        def run(self): self.help()
"""
_CLASS_BODY: Final = """\
class T(Base):
    X = make()
    def run(self): body()
"""
_METHOD_NAMED_LIKE_DECORATOR: Final = """\
def retry(f): return f
class Client:
    @retry
    def retry(self): pass
"""
_EXCEPT_AT_TOP: Final = """\
try:
    pass
except ValueError as err:
    pass
"""
_DEEP_STATEMENT: Final = "VALUE = " + "1 + " * 2000 + "make()\n"
_CLASS_LOCAL: Final = """\
class Other:
    Point = Gone = Lost = int
    del Gone
    def drop(self): del Point
    try: pass
    except E as Lost: pass
    value = Point(), Size(), Gone(), Lost()
    Size = int
"""
_TYPE_PARAMS: Final = "@deco(Point)\ndef make[Point, Size, T](p: T, q=Size): pass\n"
_OUTER_TYPE_PARAMS: Final = "class Box[Item]:\n    class In:\n        x = Item, Size\n"
_CLASS_LOCAL_COMPREHENSION: Final = """\
class Other:
    Point = int
    Size = int
    values = [[Size for _ in Point()] for Size in range(Size())]
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("def run(): b(); a(); b()\n", ["b", "a", "b"], id="call-order"),
        pytest.param(_NESTED_DEF, ["helper"], id="nested-def"),
        pytest.param(_NESTED_DEF_OUTER_PARTS, ["deco", "make"], id="outer-parts"),
        pytest.param("def run(): return lambda: helper()\n", ["helper"], id="lambda"),
        pytest.param(_COMPREHENSION_THEN_CALL, ["helper"], id="comprehension-target"),
        pytest.param(
            "def run(): return (lambda helper: helper), helper()\n",
            ["helper"],
            id="lambda-parameter",
        ),
        pytest.param(_CLASS_BODY_IN_DEF, ["x"], id="class-body-in-def"),
        pytest.param(
            "def run(items): return [helper(x) for x in items]\n",
            ["helper"],
            id="call-in-comprehension",
        ),
        pytest.param("def run(): [x for x in h()]\n", ["h"], id="first-iterable"),
        pytest.param(
            "def run(): return [helper for helper in helper()]\n",
            ["helper"],
            id="first-iterable-named-like-target",
        ),
        pytest.param(_GLOBAL, ["cache", "helper", "helper"], id="global"),
        pytest.param(_CLASS, ["helper"], id="class-methods"),
        pytest.param("def run(k=lambda: h()): pass\n", ["h"], id="lambda-default"),
    ],
)
def test_called_names_returns_names_run_when_called(
    parse: Parse, source: str, expected: list[str]
) -> None:
    assert _module_calls(parse, source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("def run(value): return value\n", [], id="parameter"),
        pytest.param(_SHADOWING_NESTED_DEF, [], id="nested-def"),
        pytest.param(_EXCEPT_ALIAS, ["ValueError"], id="except-alias"),
        pytest.param(
            "def run(): return lambda value: value\n", [], id="lambda-parameter"
        ),
        pytest.param(
            "def run(items): return [value for value in items]\n",
            [],
            id="comprehension-target",
        ),
        pytest.param(_MATCH_CAPTURE, [], id="match-capture"),
        pytest.param(_COMPREHENSION_WALRUS, [], id="comprehension-walrus"),
        pytest.param(_NONLOCAL, [], id="nonlocal"),
        pytest.param(_DOTTED_IMPORT, [], id="dotted-import"),
        pytest.param(_LOCAL_IMPORT, [], id="local-import"),
        pytest.param(_IMPORT_ALIAS, [], id="import-alias"),
    ],
)
def test_called_names_skips_shadowed_names(
    parse: Parse, source: str, expected: list[str]
) -> None:
    assert _module_calls(parse, source) == expected


def _module_calls(parse: Parse, source: str) -> list[str]:
    file = parse(source)
    return refs.called_names(file, file.tree, file.tree.body[-1])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "class T:\n    def run(self): self.b(); self.a()\n", ["b", "a"], id="self"
        ),
        pytest.param(
            "class T:\n    def run(self, /): self.help()\n",
            ["help"],
            id="positional-only",
        ),
        pytest.param(_CLASSMETHOD, ["build"], id="cls"),
        pytest.param(_STATICMETHOD, [], id="staticmethod"),
        pytest.param("class T:\n    def run(): helper()\n", [], id="no-parameters"),
        pytest.param("class T:\n    def run(self, o): o.h()\n", [], id="other-object"),
        pytest.param(_NESTED_CLASS, [], id="nested-class"),
        pytest.param(
            "class T:\n    def run(self): self.helper = 1\n", [], id="attribute-write"
        ),
        pytest.param(
            "class T:\n    def run(self): return (lambda self: self.a), self.b()\n",
            ["b"],
            id="lambda-receiver-parameter",
        ),
        pytest.param(
            "class T:\n    def run(self, items): return [self.help() for x in items]\n",
            ["help"],
            id="comprehension",
        ),
    ],
)
def test_called_names_returns_receiver_calls_in_class(
    parse: Parse, source: str, expected: list[str]
) -> None:
    assert _method_calls(parse, source) == expected


def _method_calls(parse: Parse, source: str) -> list[str]:
    file = parse(source)
    scope = file.tree.body[0]
    assert isinstance(scope, ast.ClassDef)
    return refs.called_names(file, scope, scope.body[-1])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "def run(x: Arg) -> Ret: body()\n", {"Arg", "Ret"}, id="annotations"
        ),
        pytest.param("f = lambda x=make(): body()\n", {"make"}, id="lambda-default"),
        pytest.param(_CLASS_BODY, {"Base", "make"}, id="class-body"),
        pytest.param(
            "@value.setter\ndef value(new): pass\n", set(), id="own-name-in-decorator"
        ),
        pytest.param(_METHOD_NAMED_LIKE_DECORATOR, {"retry"}, id="method-decorator"),
        pytest.param(_DEEP_STATEMENT, {"make"}, id="deep-expression"),
        pytest.param("x = [(lambda: P)() for P in t]\n", {"t"}, id="lambda-call"),
        pytest.param("x = (lambda: [P for P in t])()\n", {"t"}, id="lambda-loop"),
        pytest.param("x = (lambda: (lambda h: h)(0))()\n", set(), id="nested-lambda"),
        pytest.param("x = (lambda P: P)(0)\n", set(), id="lambda-parameter"),
    ],
)
def test_import_time_names_skips_function_bodies(
    parse: Parse, source: str, expected: set[str]
) -> None:
    file = parse(source)
    assert refs.import_time_names(file, file.tree, file.tree.body[-1]).loads == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_CLASS_LOCAL, {"E", "Gone", "Lost", "Size", "int"}, id="local"),
        pytest.param(_TYPE_PARAMS, {"Point", "Size", "deco"}, id="type-params"),
        pytest.param(_OUTER_TYPE_PARAMS, {"Size"}, id="enclosing-type-params"),
        pytest.param(
            _CLASS_LOCAL_COMPREHENSION, {"Point", "int", "range"}, id="comprehension"
        ),
    ],
)
def test_import_time_names_skips_class_local_names(
    parse: Parse, source: str, expected: set[str]
) -> None:
    file = parse(source)
    assert refs.import_time_names(file, file.tree, file.tree.body[-1]).loads == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("C: Final = 1\n", {"C"}, id="assignment"),
        pytest.param("import os.path\n", {"os"}, id="dotted-import"),
        pytest.param("from a import b as c\n", {"c"}, id="import-alias"),
        pytest.param("for x in items: pass\n", {"x"}, id="for-target"),
        pytest.param(_EXCEPT_AT_TOP, {"err"}, id="except-alias"),
        pytest.param("[(y := x) for x in items]\n", {"y"}, id="comprehension-walrus"),
        pytest.param("def run(): helper = 1\n", {"run"}, id="def"),
    ],
)
def test_bound_names_returns_names_stmt_binds(
    parse: Parse, source: str, expected: set[str]
) -> None:
    file = parse(source)
    assert refs.bound_names(file, file.tree.body[-1]) == expected
