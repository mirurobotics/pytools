from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.rules import Config, run_checks

Parse = Callable[[str], CheckInput]

_SOURCE = """\
def f():
    if a:
        if b:
            pass
"""
_FUNCLEN = Diagnostic("a.py", 1, "function f is 3 lines (limit 1)")
_FILELEN = Diagnostic("a.py", 1, "file is 4 lines (limit 1)")
_NESTDEPTH = Diagnostic(
    "a.py",
    3,
    "nesting depth is 2 (limit 1) — consider early returns or extracting a helper",
)


@pytest.mark.parametrize(
    ("exclude", "expected"),
    [
        pytest.param(frozenset(), [_FUNCLEN, _FILELEN, _NESTDEPTH], id="none"),
        pytest.param(frozenset({Rule.FUNCLEN}), [_FILELEN, _NESTDEPTH], id="funclen"),
        pytest.param(frozenset({Rule.FILELEN}), [_FUNCLEN, _NESTDEPTH], id="filelen"),
        pytest.param(frozenset({Rule.NESTDEPTH}), [_FUNCLEN, _FILELEN], id="nestdepth"),
    ],
)
def test_run_checks_honors_exclude(
    parse: Parse, exclude: frozenset[Rule], expected: list[Diagnostic]
) -> None:
    config = Config(max_func_len=1, max_file_len=1, max_nest_depth=1, exclude=exclude)
    assert run_checks(parse(_SOURCE), config) == expected
