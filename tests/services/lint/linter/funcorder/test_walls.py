from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.walls import Walls

type Parse = Callable[[str], CheckInput]

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


@pytest.mark.parametrize(
    ("moved", "passed", "expected"),
    [
        pytest.param([3], [1], True, id="past-a-calm-statement"),
        pytest.param([1], [], False, id="fixed-decl"),
        pytest.param([3], [2], False, id="past-its-binder"),
        pytest.param([0], [2], False, id="walled-past-a-barrier"),
    ],
)
def test_may_pass_reports_allowed_move(
    moved: list[int], passed: list[int], expected: bool
) -> None:
    assert _walls({0}).may_pass(moved, passed) is expected


@pytest.mark.parametrize(
    ("order", "runs", "expected"),
    [
        pytest.param([0, 1, 2, 3], {0}, True, id="same-order"),
        pytest.param([0, 2, 1, 3], {0}, True, id="calm-statements-swap"),
        pytest.param([1, 0, 2, 3], {0}, False, id="past-code-that-runs"),
        pytest.param([2, 1, 0, 3], {1}, False, id="across-code-that-stays"),
        pytest.param([0, 2, 1, 3], {1, 2}, False, id="code-that-runs-swaps"),
        pytest.param([0, 1, 3, 2], {0}, False, id="past-its-binder"),
        pytest.param([0, 2, 3, 1], {0}, False, id="past-a-rival-binding"),
    ],
)
def test_keeps_reports_safe_order(
    order: list[int], runs: set[int], expected: bool
) -> None:
    assert _walls(runs).keeps(order) is expected


def _walls(runs: set[int]) -> Walls:
    return Walls(
        binders={3: frozenset({2})},
        barriers=frozenset({0, 2}),
        walled=frozenset({0}),
        fixed=frozenset({1}),
        runs=frozenset(runs),
        rivals=[[1, 3]],
        reads={},
    )


def test_find_walls_fixes_decls_that_run_code(parse: Parse) -> None:
    expected = {3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 17, 18, 20, 23, 24, 25}
    assert _fixed(parse, _RUNS_CODE) == expected


def test_find_walls_fixes_rebound_classes(parse: Parse) -> None:
    assert _fixed(parse, _REBOUND) == {0, 2}


def _fixed(parse: Parse, source: str) -> set[int]:
    file = parse(source)
    walls = model.build(file, file.tree).walls
    return {idx for idx in range(len(file.tree.body)) if not walls.may_pass([idx], [])}
