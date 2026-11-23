import subprocess
import sys
from collections.abc import Callable
from functools import partial
from importlib.resources import files

import pytest

from pytools.services.lint import external

Call = tuple[list[str], dict[str, object]]

_CONFIG_DIR = files("pytools.services.lint")
_RUFF = ["--config", str(_CONFIG_DIR / "ruff.toml")]
_MYPY = ["--config-file", str(_CONFIG_DIR / "mypy.ini")]
_PATHS = ["src", "tests"]


@pytest.fixture
def run_calls(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """Record each subprocess.run call instead of running the tool."""
    calls: list[Call] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


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
    run_calls: list[Call], runner: Callable[[], None], tool_args: list[str]
) -> None:
    runner()
    command = [sys.executable, "-m", *tool_args, *_PATHS]
    assert run_calls == [(command, {"check": True})]
