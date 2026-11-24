from pathlib import Path
from typing import Final

import pytest

from pytools.services.lint.linter.rules import Config
from pytools.services.lint.linter.run import run_fixer, run_linter

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
_MISPLACED: Final = "def _h(): pass\ndef run(): _h()\n"
_ORDERED: Final = "def run(): _h()\ndef _h(): pass\n"


def test_run_linter_prints_and_counts_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    long_file = tmp_path / "long.py"
    long_file.write_text(_TWO_LONG_FUNCTIONS, encoding="utf-8")
    short_file = tmp_path / "short.py"
    short_file.write_text(_SHORT_FUNCTION, encoding="utf-8")
    count = run_linter([str(long_file), str(short_file)], _config())
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
    assert run_linter([str(bom_file)], _config()) == 2
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
    count = run_linter([str(bad_file)], _config())
    captured = capsys.readouterr()
    assert (count, captured.out) == (0, "")
    assert captured.err.startswith(f"warning: {bad_file}: ")


def _config() -> Config:
    return Config(max_func_len=1)


def test_run_fixer_rewrites_misplaced_file(tmp_path: Path) -> None:
    misplaced = tmp_path / "misplaced.py"
    misplaced.write_text(_MISPLACED, encoding="utf-8")
    ordered = tmp_path / "ordered.py"
    ordered.write_text(_ORDERED, encoding="utf-8")
    run_fixer([str(misplaced), str(ordered)], Config())
    assert misplaced.read_text(encoding="utf-8") == _ORDERED
    assert ordered.read_text(encoding="utf-8") == _ORDERED


def test_run_fixer_warns_and_skips_unparsable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_file = tmp_path / "bad.py"
    bad_file.write_bytes(b"def f(:\n")
    run_fixer([str(bad_file)], Config())
    assert bad_file.read_bytes() == b"def f(:\n"
    assert capsys.readouterr().err.startswith(f"warning: {bad_file}: ")
