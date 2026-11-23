import argparse

import pytest

from pytools.commands import lint
from pytools.commands.lint import add_lint_command
from pytools.services.lint.lint import LintError, LintOptions


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_lint_command(parser.add_subparsers())
    return parser.parse_args(["lint", *argv])


def _fail_lint(_opts: LintOptions) -> None:
    raise LintError


def test_add_lint_command_defaults() -> None:
    args = _parse([])
    assert (args.paths, args.fix) == (["."], True)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src", ["src"]),
        ("src,tests", ["src", "tests"]),
        (" src , ,tests, ", ["src", "tests"]),
    ],
)
def test_add_lint_command_parses_paths(raw: str, expected: list[str]) -> None:
    assert _parse(["--paths", raw]).paths == expected


@pytest.mark.parametrize("raw", ["", ",", " , "])
def test_add_lint_command_rejects_empty_paths(raw: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse(["--paths", raw])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(("flag", "expected"), [("--fix", True), ("--no-fix", False)])
def test_add_lint_command_parses_fix(flag: str, expected: bool) -> None:
    assert _parse([flag]).fix is expected


def test_lint_handler_runs_lint(lint_calls: list[LintOptions]) -> None:
    args = _parse(["--paths", "src,tests", "--no-fix"])
    args.handler(args)
    assert lint_calls == [LintOptions(paths=["src", "tests"], fix=False)]


def test_lint_handler_exits_on_lint_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lint, "run_lint", _fail_lint)
    args = _parse([])
    with pytest.raises(SystemExit) as excinfo:
        args.handler(args)
    assert isinstance(excinfo.value.__cause__, LintError)
