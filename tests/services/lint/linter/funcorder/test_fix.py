from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import funcorder

type Parse = Callable[[str], CheckInput]

_RUN: Final = "def run(x: int | None) -> list[int]: pass\n"
_PLACED: Final = "class P:\n    x: int\nX = 0\ndef run(): _h(); return P()\n"
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
            "# helps\n@cache\ndef _h(): pass\ndef run(): _h()\n",
            "def run(): _h()\n# helps\n@cache\ndef _h(): pass\n",
            id="comments-and-decorators",
        ),
        pytest.param(
            "def _h(): pass\n@overload\ndef f(x: int) -> int: ...\ndef f(x): _h()\n",
            "@overload\ndef f(x: int) -> int: ...\ndef f(x): _h()\ndef _h(): pass\n",
            id="overload-stubs",
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
            id="methodless-class-above-first-user",
        ),
        pytest.param(
            "class P:\n    x: int\ndef other(): pass\nORIGIN = P()\n",
            "def other(): pass\nclass P:\n    x: int\nORIGIN = P()\n",
            id="methodless-class-above-statement-user",
        ),
        pytest.param(
            "def _h(): pass\n" + _PLACED,
            _PLACED + "def _h(): pass\n",
            id="placed-class-stays",
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
        pytest.param(
            _SHARED_LINE,
            _SHARED_LINE.replace(
                "    def _h(self): pass\n    def run(self): self._h()\n",
                "    def run(self): self._h()\n    def _h(self): pass\n",
            ),
            id="module-with-shared-line",
        ),
    ],
)
def test_fix_orders_class_body(parse: Parse, source: str, expected: str) -> None:
    assert funcorder.fix(parse(source)) == expected


def test_fix_follows_a_long_chain(parse: Parse) -> None:
    chain = "".join(map("class C{}(C{}): pass\n".format, range(1, 1200), range(1199)))
    make = "def make(): return C1199()\n"
    source = "class C0:\n    x: int\n" + _RUN + chain + make
    expected = _RUN + "class C0:\n    x: int\n" + chain + make
    assert funcorder.fix(parse(source)) == expected
