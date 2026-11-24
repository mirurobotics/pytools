from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_OVERLOADS: Final = """\
@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x): return _convert(x)
def _convert(x): return x
"""
_OVERLOADED_CALLEE: Final = """\
def run(): return parse(1)
@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x): return x
"""
_PROPERTY: Final = """\
class T:
    @property
    def value(self): return self._load()
    @value.setter
    def value(self, new): self._store(new)
    def _load(self): pass
    def _store(self, new): pass
"""
_OVERLOADED_CALLER: Final = """\
def _convert(x): return x
@overload
def parse(x: int) -> int: ...
def parse(x): return _convert(x)
"""
_PROPERTY_GETTER: Final = """\
class T:
    def _load(self): pass
    @property
    def value(self): return self._load()
    @value.setter
    def value(self, new): pass
"""
_DECORATOR_PIN: Final = """\
def _deco(f): return f
@_deco
def run(): _deco(1)
"""
_CLASS_BODY_PIN: Final = """\
def _h(): pass
class T:
    X = _h()
    def run(self): return _h()
"""
_EXEMPT_CALLER: Final = """\
class T:
    def a(self): pass
    def _h(self): pass
    def e(self): self._h()  # nolint: funcorder
"""
_EXEMPT_METHOD_IN_GROUP: Final = """\
class T:
    def a(self): pass
    def _e(self): pass  # nolint: funcorder
    def b(self): pass
"""
_NOLINT_CLASS: Final = """\
def _helper(): pass
class Runner:  # nolint: funcorder
    def run(self): _helper()
"""
_NOLINT_METHOD: Final = """\
def _helper(): pass
class Runner:
    def run(self): _helper()  # nolint: funcorder
"""


def _diag(line: int, message: str) -> Diagnostic:
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_OVERLOADS, [], id="overloads"),
        pytest.param(_OVERLOADED_CALLEE, [], id="overloaded-callee"),
        pytest.param(_PROPERTY, [], id="property-getter-and-setter"),
        pytest.param(
            _OVERLOADED_CALLER,
            [_diag(1, '"_convert" should be below its last caller "parse"')],
            id="overloaded-caller",
        ),
        pytest.param(
            _PROPERTY_GETTER,
            [_diag(2, '"T._load" should be below its last caller "T.value"')],
            id="property-getter-caller",
        ),
    ],
)
def test_check_treats_redefined_def_as_one(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funcorder.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_DECORATOR_PIN, id="decorator"),
        pytest.param(
            "def _make(): pass\ndef run(x=_make()): return _make()\n", id="default"
        ),
        pytest.param("def _t(): pass\ndef run(x: _t): return _t()\n", id="annotation"),
        pytest.param(_CLASS_BODY_PIN, id="class-body"),
        pytest.param(
            "def _h(): pass\nVALUE = _h()\ndef run(): return _h()\n",
            id="module-statement",
        ),
    ],
)
def test_check_skips_def_used_at_import_time(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "def _helper(): pass  # nolint: funcorder\ndef run(): _helper()\n",
            id="def-line",
        ),
        pytest.param(
            "# nolint: funcorder\ndef _helper(): pass\ndef run(): _helper()\n",
            id="line-above",
        ),
        pytest.param(_EXEMPT_CALLER, id="exempt-caller"),
        pytest.param(_EXEMPT_METHOD_IN_GROUP, id="exempt-method-inside-its-group"),
    ],
)
def test_check_skips_def_with_nolint(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_NOLINT_CLASS, id="class"),
        pytest.param(_NOLINT_METHOD, id="method"),
    ],
)
def test_check_ignores_nolint_on_class_or_method(parse: Parse, source: str) -> None:
    expected = [_diag(1, '"_helper" should be below its last caller "Runner"')]
    assert funcorder.check(parse(source)) == expected
