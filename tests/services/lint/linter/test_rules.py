from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.rules import Config, run_checks

Parse = Callable[[str], CheckInput]

_SOURCE = """\
def f(parameter_name_too_long, n):
    if a:
        if b:
            pass

# stray note
"""
_FUNCLEN = Diagnostic("a.py", 1, "function f is 3 lines (limit 1)")
_FILELEN = Diagnostic("a.py", 1, "file is 4 lines (limit 1)")
_NESTDEPTH = Diagnostic(
    "a.py",
    3,
    "nesting depth is 2 (limit 1) — consider early returns or extracting a helper",
)
_NAMELEN = Diagnostic(
    "a.py", 1, 'name "parameter_name_too_long" is 23 chars (limit 20)'
)
_VARNAME = Diagnostic(
    "a.py", 1, 'variable name "n" is shorter than 3 chars; use a descriptive name'
)
_STRAYCOMMENT = Diagnostic(
    "a.py",
    6,
    "comment is not attached to a statement; remove it or move it directly above one",
)


@pytest.mark.parametrize(
    ("exclude", "expected"),
    [
        pytest.param(
            frozenset(),
            [_FUNCLEN, _FILELEN, _NESTDEPTH, _NAMELEN, _VARNAME, _STRAYCOMMENT],
            id="none",
        ),
        pytest.param(
            frozenset({Rule.FUNCLEN}),
            [_FILELEN, _NESTDEPTH, _NAMELEN, _VARNAME, _STRAYCOMMENT],
            id="funclen",
        ),
        pytest.param(
            frozenset({Rule.FILELEN}),
            [_FUNCLEN, _NESTDEPTH, _NAMELEN, _VARNAME, _STRAYCOMMENT],
            id="filelen",
        ),
        pytest.param(
            frozenset({Rule.NESTDEPTH}),
            [_FUNCLEN, _FILELEN, _NAMELEN, _VARNAME, _STRAYCOMMENT],
            id="nestdepth",
        ),
        pytest.param(
            frozenset({Rule.NAMELEN}),
            [_FUNCLEN, _FILELEN, _NESTDEPTH, _VARNAME, _STRAYCOMMENT],
            id="namelen",
        ),
        pytest.param(
            frozenset({Rule.VARNAME}),
            [_FUNCLEN, _FILELEN, _NESTDEPTH, _NAMELEN, _STRAYCOMMENT],
            id="varname",
        ),
        pytest.param(
            frozenset({Rule.STRAYCOMMENT}),
            [_FUNCLEN, _FILELEN, _NESTDEPTH, _NAMELEN, _VARNAME],
            id="straycomment",
        ),
    ],
)
def test_run_checks_honors_exclude(
    parse: Parse, exclude: frozenset[Rule], expected: list[Diagnostic]
) -> None:
    config = Config(max_func_len=1, max_file_len=1, max_nest_depth=1, exclude=exclude)
    assert run_checks(parse(_SOURCE), config) == expected
