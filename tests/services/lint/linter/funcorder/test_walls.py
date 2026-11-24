from typing import Final

import pytest

from pytools.services.lint.linter.funcorder.walls import Walls

_WALLS: Final = Walls(
    binders={3: frozenset({2})},
    barriers=frozenset({0, 2}),
    walled=frozenset(),
    runs=frozenset({0}),
)


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        pytest.param([0, 1, 2, 3], True, id="same-order"),
        pytest.param([0, 2, 3, 1], True, id="decl-below-its-binder"),
        pytest.param([1, 0, 2, 3], False, id="past-code-that-runs"),
        pytest.param([0, 1, 3, 2], False, id="past-its-binder"),
    ],
)
def test_keeps_reports_safe_order(order: list[int], expected: bool) -> None:
    assert _WALLS.keeps(order) is expected
