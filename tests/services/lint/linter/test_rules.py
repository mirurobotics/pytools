from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.rules import Config, run_checks

Parse = Callable[[str], CheckInput]

_SOURCE = """\
def f():
    a = 1
    b = 2
"""


@pytest.mark.parametrize(
    ("exclude", "expected"),
    [
        (frozenset(), [Diagnostic("a.py", 1, "function f is 2 lines (limit 1)")]),
        (frozenset({Rule.FUNCLEN}), []),
    ],
)
def test_run_checks_honors_exclude(
    parse: Parse, exclude: frozenset[Rule], expected: list[Diagnostic]
) -> None:
    config = Config(max_func_len=1, exclude=exclude)
    assert run_checks(parse(_SOURCE), config) == expected
