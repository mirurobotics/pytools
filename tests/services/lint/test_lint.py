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
from pytools.services.lint.linter.rules import Config

Call = tuple[str, list[str], bool | Config | None]

_PATHS = ["src", "tests"]
_FILES = ["src/a.py", "tests/test_a.py"]
_CONFIG = Config()
_VIOLATIONS = 2
_SUCCESS_OUTPUT = (
    "Running ruff check...\n"
    "Running ruff format...\n"
    "Running custom linter...\n"
    "Running mypy...\n"
    "\n"
    "Timings\n"
    "-------\n"
    "ruff check          0.0s\n"
    "ruff format         0.0s\n"
    "custom linter       0.0s\n"
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

    def record(name: str, paths: list[str], arg: bool | Config | None) -> bool:
        calls.append((name, paths, arg))
        return name not in failing

    def list_python_files(paths: list[str]) -> list[str] | None:
        return _FILES if record("list python files", paths, None) else None

    def run_linter(files: list[str], config: Config) -> int:
        return 0 if record("custom linter", files, config) else _VIOLATIONS

    monkeypatch.setattr(external, "list_python_files", list_python_files)
    monkeypatch.setattr(lint, "run_linter", run_linter)
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
    lint.run_lint(LintOptions(paths=_PATHS, fix=fix, linter_config=_CONFIG))
    assert calls == [
        ("ruff check", _PATHS, fix),
        ("ruff format", _PATHS, fix),
        ("list python files", _PATHS, None),
        ("custom linter", _FILES, _CONFIG),
        ("mypy", _PATHS, None),
    ]
    assert capsys.readouterr().out == _SUCCESS_OUTPUT


def test_run_lint_collects_failures_from_every_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _fake_external(monkeypatch, failing={"ruff format", "mypy"})
    with pytest.raises(LintError):
        lint.run_lint(LintOptions(paths=_PATHS, fix=True, linter_config=_CONFIG))
    assert [call[0] for call in calls] == [
        "ruff check",
        "ruff format",
        "list python files",
        "custom linter",
        "mypy",
    ]
    assert "Lint complete" not in capsys.readouterr().out


def test_run_lint_fails_custom_linter_on_violations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_external(monkeypatch, failing={"custom linter"})
    with pytest.raises(LintError):
        lint.run_lint(LintOptions(paths=_PATHS, fix=True, linter_config=_CONFIG))
    out = capsys.readouterr().out
    assert "Running custom linter...\n2 violation(s) found.\n" in out


def test_run_lint_fails_custom_linter_on_list_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_external(monkeypatch, failing={"list python files"})
    with pytest.raises(LintError):
        lint.run_lint(LintOptions(paths=_PATHS, fix=True, linter_config=_CONFIG))
    assert [call[0] for call in calls] == [
        "ruff check",
        "ruff format",
        "list python files",
        "mypy",
    ]


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
