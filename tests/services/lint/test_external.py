import subprocess
import sys
from collections.abc import Callable
from functools import partial
from importlib.resources import files
from pathlib import Path

import pytest

from pytools.services.lint import external

type Call = tuple[list[str], dict[str, object]]


def _ruff_config() -> list[str]:
    return ["--config", str(files("pytools.services.lint") / "ruff.toml")]


def _mypy_config() -> list[str]:
    return ["--config-file", str(files("pytools.services.lint") / "mypy.ini")]


def _paths() -> list[str]:
    return ["src", "tests"]


def test_list_python_files_lists_relative_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    cwd = Path.cwd()
    listed = [cwd / "src" / "a.py", cwd / "stub.pyi", cwd.parent / "b.py"]
    calls = _fake_run(monkeypatch, 0, "".join(f"{path}\n" for path in listed))
    python_files = external.list_python_files(_paths())
    args = ["check", "--show-files", *_ruff_config(), *_paths()]
    command = [sys.executable, "-m", "ruff", *args]
    kwargs = {"stdout": subprocess.PIPE, "text": True, "check": False}
    assert python_files == [str(Path("src", "a.py")), str(Path("..", "b.py"))]
    assert calls == [(command, kwargs)]


def test_list_python_files_is_none_when_ruff_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_run(monkeypatch, 2)
    assert external.list_python_files(_paths()) is None


@pytest.mark.parametrize(("returncode", "passed"), [(0, True), (1, False)])
@pytest.mark.parametrize(
    ("runner", "tool_args"),
    [
        (
            partial(external.run_ruff_format, _paths(), fix=True),
            ["ruff", "format", *_ruff_config()],
        ),
        (
            partial(external.run_ruff_format, _paths(), fix=False),
            ["ruff", "format", "--check", *_ruff_config()],
        ),
        (
            partial(external.run_ruff_check, _paths(), fix=True),
            ["ruff", "check", "--fix", *_ruff_config()],
        ),
        (
            partial(external.run_ruff_check, _paths(), fix=False),
            ["ruff", "check", *_ruff_config()],
        ),
        (partial(external.run_mypy, _paths()), ["mypy", *_mypy_config()]),
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
    command = [sys.executable, "-m", *tool_args, *_paths()]
    assert (runner(), calls) == (passed, [(command, {"check": False})])


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
