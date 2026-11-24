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
_DEEP_STATEMENT: Final = "VALUE = " + "1 + " * 2000 + "make()\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("def run(): b(); a(); b()\n", ["b", "a", "b"], id="call-order"),
        pytest.param(_NESTED_DEF, ["helper"], id="nested-def"),
        pytest.param(
            _NESTED_DEF_OUTER_PARTS, ["deco", "make"], id="nested-def-outer-parts"
        ),
        pytest.param("def run(): return lambda: helper()\n", ["helper"], id="lambda"),
        pytest.param(_COMPREHENSION_THEN_CALL, ["helper"], id="comprehension-target"),
        pytest.param(
            "def run(): return (lambda helper: helper), helper()\n",
            ["helper"],
            id="lambda-parameter",
        ),
        pytest.param(_CLASS_BODY_IN_DEF, ["x"], id="class-body-in-def"),
        pytest.param(_CLASS, ["helper"], id="class-methods"),
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
        pytest.param(
            "class T:\n    def run(self, other): other.help()\n",
            [],
            id="other-object",
        ),
        pytest.param(_NESTED_CLASS, [], id="nested-class"),
        pytest.param(
            "class T:\n    def run(self): self.helper = 1\n", [], id="attribute-write"
        ),
        pytest.param(
            "class T:\n    def run(self): return (lambda self: self.a), self.b()\n",
            ["b"],
            id="lambda-receiver-parameter",
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
        pytest.param(_DEEP_STATEMENT, {"make"}, id="deep-expression"),
    ],
)
def test_import_time_names_skips_function_bodies(
    parse: Parse, source: str, expected: set[str]
) -> None:
    assert refs.import_time_names(parse(source).tree.body) == expected
