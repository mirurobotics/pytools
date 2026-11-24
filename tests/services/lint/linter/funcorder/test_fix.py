from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_RUN: Final = "def run(x: int | None) -> list[int]: pass\n"
_PLACED: Final = "class P:\n    x: int\nX = 0\ndef run(): _h(); return P()\n"
_DEEPER: Final = "class Point:\n    x: int\nclass Line:\n    start: Point\n"
_SIDE_EFFECTS: Final = """\
ids = iter(range(2))
def _a(x=next(ids)): return x
def b(x=next(ids)): return x
"""
_DYNAMIC_USE: Final = """\
def _h(): return 1
result = globals()["_h"]()
def run(): return _h()
"""
_RENAMED_DECORATOR: Final = """\
from framework import route as cache
@cache("/admin")
def _h(): pass
def run(): _h()
"""
_REBOUND: Final = "def _h(): return 1\n_h = 2\ndef run(): return _h\n"
_NEAR_USER: Final = """\
def main(): U()
class P:
    x: int
S = 1
def U(p: P): pass
def W(x=S): pass
"""
_NEAR_USER_FIXED: Final = """\
def main(): U()
class P:
    x: int
def U(p: P): pass
S = 1
def W(x=S): pass
"""
_SHARED_USER: Final = """\
def main(): V(); U()
class A:
    x: int
class B:
    y: int
def U(): return A(), B()
def V(): return B()
"""
_SHARED_USER_FIXED: Final = """\
def main(): V(); U()
class B:
    y: int
def V(): return B()
class A:
    x: int
def U(): return A(), B()
"""
_TRAILING_COMMENT: Final = """\
class T:
    def _h(self):
        return 1
        # TODO: cache this
    def run(self):
        return self._h()
"""
_TRAILING_COMMENT_FIXED: Final = """\
class T:
    def run(self):
        return self._h()
    def _h(self):
        return 1
        # TODO: cache this
"""
_SHARED_LINE: Final = """\
a = 1; b = 2
def _h(): pass
def run(): _h()
class T:
    def _h(self): pass
    def run(self): self._h()
"""


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("def run(): _h()\ndef _h(): pass\n", id="ordered"),
        pytest.param("a = 1; b = 2\ndef _h(): pass\ndef run(): _h()\n", id="shared"),
        pytest.param(_SIDE_EFFECTS, id="definitions-with-side-effects"),
        pytest.param(_DYNAMIC_USE, id="statement-that-runs-code"),
        pytest.param(_RENAMED_DECORATOR, id="decorated-definition"),
        pytest.param(_REBOUND, id="name-bound-again"),
    ],
)
def test_fix_skips_source_it_cannot_order(parse: Parse, source: str) -> None:
    assert funcorder.fix(parse(source)) is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "def _h(): pass\ndef run(): _h()\n",
            "def run(): _h()\ndef _h(): pass\n",
            id="stepdown",
        ),
        pytest.param(
            "def a(): _b()\ndef _b(): pass\ndef main(): a()\n",
            "def main(): a()\ndef a(): _b()\ndef _b(): pass\n",
            id="helpers-move-with-their-caller",
        ),
        pytest.param(
            "import x\n# helps\ndef _h(): pass\ndef run(): _h()\n",
            "import x\ndef run(): _h()\n# helps\ndef _h(): pass\n",
            id="attached-comment",
        ),
        pytest.param(
            "#!/usr/bin/env python3\ndef _h(): pass\ndef run(): _h()\n",
            "#!/usr/bin/env python3\ndef run(): _h()\ndef _h(): pass\n",
            id="file-header-stays",
        ),
        pytest.param(
            "def _h(): pass\ndef run(): _h() \\\n# joined\n",
            "def run(): _h() \\\n# joined\ndef _h(): pass\n",
            id="backslash-continuation",
        ),
        pytest.param(
            "def _h(): pass\nN = 3\ndef _g(): return N\ndef main(): _h(); _g()\n",
            "def main(): _h(); _g()\ndef _h(): pass\nN = 3\ndef _g(): return N\n",
            id="carried-statement",
        ),
        pytest.param(
            "def _x(): pass\ndef y(): pass  # nolint: funcorder\ndef z(): pass\n",
            "def y(): pass  # nolint: funcorder\ndef z(): pass\ndef _x(): pass\n",
            id="private-entry-moves-below-public",
        ),
        pytest.param(
            "class Point:\n    x: int\ndef other(): pass\ndef make(): return Point()\n",
            "def other(): pass\nclass Point:\n    x: int\ndef make(): return Point()\n",
            id="methodless-class-down-to-first-user",
        ),
        pytest.param(
            "def make(): return Point()\ndef other(): pass\nclass Point:\n    x: int\n",
            "class Point:\n    x: int\ndef make(): return Point()\ndef other(): pass\n",
            id="methodless-class-up-to-first-user",
        ),
        pytest.param(
            "class P:\n    x: int\ndef other(): pass\nORIGIN = P()\n",
            "def other(): pass\nclass P:\n    x: int\nORIGIN = P()\n",
            id="methodless-class-above-statement-user",
        ),
        pytest.param(
            _DEEPER + "def other(): pass\ndef make(): return Line()\n",
            "def other(): pass\n" + _DEEPER + "def make(): return Line()\n",
            id="deeper-class-above-its-user",
        ),
        pytest.param(
            "class B:\n    y: int\ndef other(): pass\nclass A:\n    x: int\n"
            "def make(a: A, b: B): pass\n",
            "def other(): pass\nclass B:\n    y: int\nclass A:\n    x: int\n"
            "def make(a: A, b: B): pass\n",
            id="same-depth-classes-keep-their-order",
        ),
        pytest.param(
            "class P:\n    x: int\ndef f(): return P()\ndef g(): f(); return P()\n",
            "class P:\n    x: int\ndef g(): f(); return P()\ndef f(): return P()\n",
            id="methodless-class-above-new-first-user",
        ),
        pytest.param(
            "def _h(): pass\n" + _PLACED,
            _PLACED + "def _h(): pass\n",
            id="placed-class-stays",
        ),
        pytest.param(_NEAR_USER, _NEAR_USER_FIXED, id="near-class-follows-its-user"),
        pytest.param(
            _SHARED_USER, _SHARED_USER_FIXED, id="near-class-whose-neighbour-moves"
        ),
    ],
)
def test_fix_orders_module(parse: Parse, source: str, expected: str) -> None:
    fixed = funcorder.fix(parse(source))
    assert fixed == expected
    assert funcorder.check(parse(expected)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "class T:\n    def _h(self): pass\n    def run(self): self._h()\n",
            "class T:\n    def run(self): self._h()\n    def _h(self): pass\n",
            id="method",
        ),
        pytest.param(
            "class T:\n    def _h(self): pass\n    def run(self): self._h()\n"
            "def _g(): pass\ndef main(): _g(); T()\n",
            "class T:\n    def run(self): self._h()\n    def _h(self): pass\n"
            "def main(): _g(); T()\ndef _g(): pass\n",
            id="class-in-a-moving-module",
        ),
        pytest.param(_TRAILING_COMMENT, _TRAILING_COMMENT_FIXED, id="trailing-comment"),
    ],
)
def test_fix_orders_class_body(parse: Parse, source: str, expected: str) -> None:
    fixed = funcorder.fix(parse(source))
    assert fixed == expected
    assert funcorder.check(parse(expected)) == []


def test_fix_leaves_scope_with_shared_line(parse: Parse) -> None:
    expected = _SHARED_LINE.replace(
        "    def _h(self): pass\n    def run(self): self._h()\n",
        "    def run(self): self._h()\n    def _h(self): pass\n",
    )
    assert funcorder.fix(parse(_SHARED_LINE)) == expected


def test_fix_follows_a_long_chain(parse: Parse) -> None:
    chain = "".join(map("class C{}(C{}): pass\n".format, range(1, 1200), range(1199)))
    make = "def make(): return C1199()\n"
    source = "class C0:\n    x: int\n" + _RUN + chain + make
    expected = _RUN + "class C0:\n    x: int\n" + chain + make
    assert funcorder.fix(parse(source)) == expected


@pytest.mark.parametrize(
    "fixed",
    [
        pytest.param("def run(): _h()\n", id="dropped-statement"),
        pytest.param("def run(): _h()\ndef _h(): return 1\n", id="changed-statement"),
        pytest.param("def run(): _h(\ndef _h(): pass\n", id="unparsable"),
    ],
)
def test_holds_same_statements_rejects_other_source(parse: Parse, fixed: str) -> None:
    file = parse("def _h(): pass\ndef run(): _h()\n")
    assert not funcorder._holds_same_statements(file, fixed)
