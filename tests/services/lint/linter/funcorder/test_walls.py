import pytest

from pytools.services.lint.linter.funcorder.walls import Walls


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
        walled=frozenset(),
        runs=frozenset(runs),
        rivals=[[1, 3]],
        fixed=frozenset(),
    )
