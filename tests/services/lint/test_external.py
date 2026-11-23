import subprocess
import sys
from collections.abc import Callable
from functools import partial
from importlib.resources import files
from pathlib import Path

import pytest

from pytools.services.lint import external

Call = tuple[list[str], dict[str, object]]

_CONFIG_DIR = files("pytools.services.lint")
_RUFF = ["--config", str(_CONFIG_DIR / "ruff.toml")]
_MYPY = ["--config-file", str(_CONFIG_DIR / "mypy.ini")]
_PATHS = ["src", "tests"]


def _fake_run(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str = ""
) -> list[Call]:
    calls: list[Call] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_list_python_files_lists_py_files_relative_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    cwd = Path.cwd()
    listed = [cwd / "src" / "a.py", cwd / "stub.pyi", cwd.parent / "b.py"]
    calls = _fake_run(monkeypatch, 0, "".join(f"{path}\n" for path in listed))
    python_files = external.list_python_files(_PATHS)
    command = [sys.executable, "-m", "ruff", "check", "--show-files", *_RUFF, *_PATHS]
    kwargs = {"stdout": subprocess.PIPE, "text": True, "check": False}
    assert python_files == [str(Path("src", "a.py")), str(Path("..", "b.py"))]
    assert calls == [(command, kwargs)]


def test_list_python_files_returns_none_when_ruff_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_run(monkeypatch, 2)
    assert external.list_python_files(_PATHS) is None


@pytest.mark.parametrize(("returncode", "passed"), [(0, True), (1, False)])
@pytest.mark.parametrize(
    ("runner", "tool_args"),
    [
        (
            partial(external.run_ruff_format, _PATHS, fix=True),
            ["ruff", "format", *_RUFF],
        ),
        (
            partial(external.run_ruff_format, _PATHS, fix=False),
            ["ruff", "format", "--check", *_RUFF],
        ),
        (
            partial(external.run_ruff_check, _PATHS, fix=True),
            ["ruff", "check", "--fix", *_RUFF],
        ),
        (
            partial(external.run_ruff_check, _PATHS, fix=False),
            ["ruff", "check", *_RUFF],
        ),
        (partial(external.run_mypy, _PATHS), ["mypy", *_MYPY]),
    ],
)
def test_runner_runs_tool_with_shared_config(
    monkeypatch: pytest.MonkeyPatch,
    runner: Callable[[], bool],
    tool_args: list[str],
    returncode: int,
    passed: bool,
) -> None:
    calls = _fake_run(monkeypatch, returncode)
    command = [sys.executable, "-m", *tool_args, *_PATHS]
    assert (runner(), calls) == (passed, [(command, {"check": False})])
