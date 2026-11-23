import subprocess
from types import SimpleNamespace

import pytest

from pytools.services.lint import external, lint
from pytools.services.lint.lint import (
    LintError,
    LintOptions,
    _format_duration,
    _print_timings,
    _StepResult,
)

Call = tuple[str, list[str], bool | None]

_PATHS = ["src", "tests"]
_SUCCESS_OUTPUT = (
    "Running ruff format...\n"
    "Running ruff check...\n"
    "Running mypy...\n"
    "\n"
    "Timings\n"
    "-------\n"
    "ruff format         0.0s\n"
    "ruff check          0.0s\n"
    "mypy                0.0s\n"
    "total               0.0s\n"
    "Lint complete\n"
)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every step and the total take zero seconds."""
    monkeypatch.setattr(lint, "time", SimpleNamespace(monotonic=lambda: 0.0))


def _fake_external(monkeypatch: pytest.MonkeyPatch, failing: set[str]) -> list[Call]:
    calls: list[Call] = []

    def record(name: str, paths: list[str], fix: bool | None) -> None:
        calls.append((name, paths, fix))
        if name in failing:
            raise subprocess.CalledProcessError(1, name)

    monkeypatch.setattr(
        external,
        "run_ruff_format",
        lambda paths, *, fix: record("ruff format", paths, fix),
    )
    monkeypatch.setattr(
        external,
        "run_ruff_check",
        lambda paths, *, fix: record("ruff check", paths, fix),
    )
    monkeypatch.setattr(external, "run_mypy", lambda paths: record("mypy", paths, None))
    return calls


@pytest.mark.usefixtures("frozen_clock")
@pytest.mark.parametrize("fix", [True, False])
def test_run_lint_runs_every_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], fix: bool
) -> None:
    calls = _fake_external(monkeypatch, failing=set())
    lint.run_lint(LintOptions(paths=_PATHS, fix=fix))
    assert calls == [
        ("ruff format", _PATHS, fix),
        ("ruff check", _PATHS, fix),
        ("mypy", _PATHS, None),
    ]
    assert capsys.readouterr().out == _SUCCESS_OUTPUT


def test_run_lint_collects_failures_from_every_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _fake_external(monkeypatch, failing={"ruff format", "mypy"})
    with pytest.raises(LintError):
        lint.run_lint(LintOptions(paths=_PATHS, fix=True))
    assert [call[0] for call in calls] == ["ruff format", "ruff check", "mypy"]
    assert "Lint complete" not in capsys.readouterr().out


def test_print_timings(capsys: pytest.CaptureFixture[str]) -> None:
    results = [
        _StepResult("ruff format", 0.4, failed=False),
        _StepResult("mypy", 465.0, failed=True),
    ]
    _print_timings(results, 490.0)
    assert capsys.readouterr().out == (
        "\nTimings\n-------\n"
        "ruff format         0.4s\n"
        "mypy               7m45s\n"
        "total              8m10s\n"
    )


def test_print_timings_widens_for_long_step_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_timings([_StepResult("a-very-long-step-name", 1.0, failed=False)], 2.0)
    assert capsys.readouterr().out == (
        "\nTimings\n-------\n"
        "a-very-long-step-name    1.0s\n"
        "total                    2.0s\n"
    )


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "0.0s"),
        (0.5, "0.5s"),
        (3.2, "3.2s"),
        (59.9, "59.9s"),
        (59.96, "1m00s"),
        (60.0, "1m00s"),
        (465.0, "7m45s"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert _format_duration(seconds) == expected
