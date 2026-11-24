import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from pytools.services.lint import external
from pytools.services.lint.linter.rules import Config
from pytools.services.lint.linter.run import run_linter


class LintError(Exception):
    """One or more lint steps failed."""


@dataclass(frozen=True)
class LintOptions:
    """Options for the lint orchestrator."""

    paths: list[str]
    fix: bool
    linter_config: Config


def run_lint(opts: LintOptions) -> None:
    """Run every lint step, raising LintError if any fails."""
    start = time.monotonic()
    results = _run_steps(opts)
    _print_timings(results, time.monotonic() - start)
    failures = [result.name for result in results if result.failed]
    if failures:
        raise LintError(f"lint failed: {', '.join(failures)}")
    _write("Lint complete")


@dataclass(frozen=True)
class _StepResult:
    name: str
    seconds: float
    failed: bool


def _run_steps(opts: LintOptions) -> list[_StepResult]:
    steps = [
        ("ruff check", lambda: external.run_ruff_check(opts.paths, fix=opts.fix)),
        ("ruff format", lambda: external.run_ruff_format(opts.paths, fix=opts.fix)),
        ("custom linter", lambda: _run_custom_linter(opts)),
        ("mypy", lambda: external.run_mypy(opts.paths)),
    ]
    return [_timed_run(name, run) for name, run in steps]


def _run_custom_linter(opts: LintOptions) -> bool:
    files = external.list_python_files(opts.paths)
    if files is None:
        return False
    count = run_linter(files, opts.linter_config, fix=opts.fix)
    if count:
        _write(f"{count} violation(s) found.")
    return count == 0


def _timed_run(name: str, run: Callable[[], bool]) -> _StepResult:
    _write(f"Running {name}...")
    start = time.monotonic()
    passed = run()
    return _StepResult(name, time.monotonic() - start, failed=not passed)


def _print_timings(results: list[_StepResult], total_seconds: float) -> None:
    rows = [(result.name, result.seconds) for result in results]
    rows.append(("total", total_seconds))
    width = max([16, *(len(name) for name, _ in rows)])
    lines = ["", "Timings", "-------"]
    for name, seconds in rows:
        lines.append(f"{name:<{width}} {_format_duration(seconds):>7}")
    _write("\n".join(lines))


def _format_duration(seconds: float) -> str:
    rounded = round(seconds, 1)
    if rounded < 60:
        return f"{rounded:.1f}s"
    minutes, remainder = divmod(round(rounded), 60)
    return f"{minutes}m{remainder:02d}s"


def _write(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()
