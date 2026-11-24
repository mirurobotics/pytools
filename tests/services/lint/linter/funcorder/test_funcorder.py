from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_RECURSION: Final = """\
def run(): _a()
def _a(): _a(); _b()
def _b(): _a(); _z()
def _z(): pass
"""
_SHARED_HELPER: Final = """\
def a(): _a1(); _h()
def _a1(): pass
def b(): _b1(); _h()
def _b1(): pass
def _h(): pass
"""
_DUNDERS: Final = """\
def __getattr__(name): return _load(name)
def _load(name): pass
def main(): _run()
def _run(): pass
"""
_SHADOWED_RECEIVER: Final = """\
class T:
    def help(self): pass
    def run(self, items):
        for self in items:
            self.help()
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
_CLASS_ABOVE_CALLEE: Final = """\
def run(): return _make()
class Point:
    x: int
def _make(): return Point()
"""
_CLASS_STAYS_BETWEEN: Final = """\
def h(): return P()
X = 1
def run(): _f()
class P:
    x = X
def _f(): pass
"""
_STEPDOWN: Final = """\
def _helper(): pass
def _other(): _helper()
def run(): _other(); return _helper
"""
_SHARED_HELPER_ABOVE: Final = """\
def a(): _a1(); _h()
def _h(): pass
def _a1(): pass
def b(): _b1(); _h()
def _b1(): pass
"""
_PUBLIC_CALLED_IN_FILE: Final = """\
def load(path): return _load_file(path)
def parse(data): return _validate(data)
def _load_file(path): return parse(_read(path))
def _read(path): return b""
def _validate(data): return len(data)
"""
_CLASS_CALLER: Final = """\
def get(): return 1
def run(): return get()
class T:
    def value(self): return run() + _help()
def _help(): return 1
"""
_DEEP_EXPRESSION: Final = (
    "def _h(): pass\ndef run(): return " + "1 + " * 2000 + "_h()\n"
)
_MAIN_GUARD: Final = """\
def _helper(): pass
def main(): _helper()
if __name__ == "__main__":
    main()
"""
_PUBLIC_METHOD_ENTRY: Final = """\
class T:
    def _a(self): pass
    def b(self): pass
"""
_METHODS: Final = """\
class T:
    def _helper(self): pass
    def run(self): self._helper(); self.run()
"""
_NESTED_CLASS: Final = """\
class Outer:
    class Inner:
        def _h(self): pass
        def run(self): self._h()
"""


def _diag(line: int, message: str) -> Diagnostic:
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "def run(): _a(); _b()\ndef _a(): _c()\ndef _b(): _c()\ndef _c(): pass\n",
            id="stepdown",
        ),
        pytest.param(_RECURSION, id="recursion-and-cycles"),
        pytest.param(
            "def _get(): return get()\ndef get(): return 1\n",
            id="public-callee-below-private-caller",
        ),
        pytest.param(_SHARED_HELPER, id="shared-helper-below-last-caller"),
        pytest.param(
            "def run(): _a()\ndef _a(): _b()\ndef _b(): _a()\ndef other(): pass\n",
            id="cycle-member-is-not-an-entry-point",
        ),
        pytest.param(
            "def _c(): pass\ndef _a(): b()\ndef b(): _a()\n",
            id="public-cycle-member-is-not-an-entry-point",
        ),
        pytest.param(
            "def run(): _helper()\ndef _helper(): pass\ndef _unused(): pass\n",
            id="public-entry-above-private-entry",
        ),
        pytest.param(_DUNDERS, id="dunder-entry-points"),
        pytest.param(
            "def value(): pass\ndef run(): value = 1; return value\n",
            id="shadowing-local",
        ),
        pytest.param(_SHADOWED_RECEIVER, id="shadowed-receiver"),
        pytest.param(
            "def helper(): pass\ndef build(): return config.helper, dict(helper=1)\n",
            id="attribute-and-keyword",
        ),
        pytest.param(
            "def _helper(): pass  # nolint: funcorder\ndef run(): _helper()\n",
            id="exempt-function",
        ),
        pytest.param(
            "# nolint: funcorder\ndef _helper(): pass\ndef run(): _helper()\n",
            id="exempt-function-line-above",
        ),
        pytest.param(_EXEMPT_CALLER, id="exempt-caller"),
        pytest.param(_EXEMPT_METHOD_IN_GROUP, id="exempt-method-inside-its-group"),
        pytest.param(_CLASS_ABOVE_CALLEE, id="methodless-class-above-callee"),
        pytest.param(
            "def helper(): pass\ndef run(v=(lambda: helper())()): pass\n",
            id="lambda-called-in-a-default",
        ),
    ],
)
def test_check_skips_ordered_source(parse: Parse, source: str) -> None:
    assert funcorder.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            _STEPDOWN,
            [
                _diag(1, '"_helper" should be below its last caller "run"'),
                _diag(2, '"_other" should be below its last caller "run"'),
            ],
            id="stepdown",
        ),
        pytest.param(
            _SHARED_HELPER_ABOVE,
            [
                _diag(2, '"_h" should be below its last caller "b"'),
                _diag(3, '"_a1" should be directly below "a"'),
            ],
            id="shared-helper-below-last-caller",
        ),
        pytest.param(
            _PUBLIC_CALLED_IN_FILE,
            [
                _diag(2, '"parse" should be below its last caller "_load_file"'),
                _diag(3, '"_load_file" should be directly below "load"'),
                _diag(4, '"_read" should be directly below "_validate"'),
                _diag(5, '"_validate" should be directly below "parse"'),
            ],
            id="public-called-in-file",
        ),
        pytest.param(
            "def _unused(): pass\ndef run(): pass\n",
            [_diag(2, '"run" should be above private "_unused"')],
            id="public-entry-first",
        ),
        pytest.param(
            _CLASS_CALLER,
            [
                _diag(1, '"get" should be below its last caller "run"'),
                _diag(2, '"run" should be below its last caller "T"'),
                _diag(5, '"_help" should be directly below "get"'),
            ],
            id="class-is-one-caller",
        ),
        pytest.param(
            "async def _h(): pass\nasync def run(): await _h()\n",
            [_diag(1, '"_h" should be below its last caller "run"')],
            id="async",
        ),
        pytest.param(
            _DEEP_EXPRESSION,
            [_diag(1, '"_h" should be below its last caller "run"')],
            id="deep-expression",
        ),
        pytest.param(
            _MAIN_GUARD,
            [_diag(1, '"_helper" should be below its last caller "main"')],
            id="main-guard",
        ),
        pytest.param(
            _CLASS_STAYS_BETWEEN,
            [_diag(6, '"_f" should be directly below "run"')],
            id="methodless-class-that-stays-between",
        ),
        pytest.param(
            "def _h(): pass\ndef run(key=lambda: _h()): pass\n",
            [_diag(1, '"_h" should be below its last caller "run"')],
            id="lambda-in-a-default",
        ),
    ],
)
def test_check_reports_def_out_of_order(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funcorder.check(parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            _PUBLIC_METHOD_ENTRY,
            [_diag(3, '"T.b" should be above private "T._a"')],
            id="public-method-entry-first",
        ),
        pytest.param(
            _METHODS,
            [_diag(2, '"T._helper" should be below its last caller "T.run"')],
            id="self",
        ),
        pytest.param(
            _NESTED_CLASS,
            [_diag(3, '"Inner._h" should be below its last caller "Inner.run"')],
            id="nested-class",
        ),
    ],
)
def test_check_reports_method_out_of_order(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert funcorder.check(parse(source)) == expected
