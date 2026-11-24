from pathlib import Path
from typing import Final

import pytest

from pytools.services.lint.linter.rules import Config
from pytools.services.lint.linter.run import run_linter

_TWO_LONG_FUNCTIONS: Final = """\
def f():
    a = 1
    b = 2


def g():
    a = 1
    b = 2
"""
_SHORT_FUNCTION: Final = """\
def h():
    return 1
"""


def test_run_linter_prints_and_counts_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    long_file = tmp_path / "long.py"
    long_file.write_text(_TWO_LONG_FUNCTIONS, encoding="utf-8")
    short_file = tmp_path / "short.py"
    short_file.write_text(_SHORT_FUNCTION, encoding="utf-8")
    count = run_linter([str(long_file), str(short_file)], _config(), fix=False)
    assert capsys.readouterr().out.splitlines() == [
        f"{long_file}:1: function f is 2 lines (limit 1)",
        f"{long_file}:6: function g is 2 lines (limit 1)",
    ]
    assert count == 2


def test_run_linter_reads_file_with_byte_order_mark(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bom_file = tmp_path / "bom.py"
    bom_file.write_text(_TWO_LONG_FUNCTIONS, encoding="utf-8-sig")
    assert run_linter([str(bom_file)], _config(), fix=False) == 2
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"def f(:\n", id="syntax-error"),
        pytest.param(b"\xff\n", id="not-utf-8"),
    ],
)
def test_run_linter_warns_and_skips_unparsable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes
) -> None:
    bad_file = tmp_path / "bad.py"
    bad_file.write_bytes(content)
    count = run_linter([str(bad_file)], _config(), fix=False)
    captured = capsys.readouterr()
    assert (count, captured.out) == (0, "")
    assert captured.err.startswith(f"warning: {bad_file}: ")


def _config() -> Config:
    return Config(max_func_len=1)
