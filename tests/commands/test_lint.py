import argparse
from enum import StrEnum

import pytest

from pytools.commands import lint
from pytools.commands.lint import add_lint_command
from pytools.services.lint.lint import LintError, LintOptions
from pytools.services.lint.linter.analysis.analysis import Rule
from pytools.services.lint.linter.rules import Config


class _TwoRules(StrEnum):
    FUNCLEN = "funclen"
    OTHER = "other"


_DEFAULT_CONFIG = Config(max_func_len=30, max_file_len=300, exclude=frozenset())


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_lint_command(parser.add_subparsers())
    return parser.parse_args(["lint", *argv])


def _fail_lint(_opts: LintOptions) -> None:
    raise LintError


def test_add_lint_command_defaults() -> None:
    args = _parse([])
    defaults = (
        args.paths,
        args.fix,
        args.max_func_len,
        args.max_file_len,
        args.exclude,
        args.rule,
    )
    assert defaults == (["."], True, 30, 300, frozenset(), None)


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


def test_add_lint_command_parses_max_func_len() -> None:
    assert _parse(["--max-func-len", "50"]).max_func_len == 50


@pytest.mark.parametrize("raw", ["0", "-1", "ten"])
def test_add_lint_command_rejects_bad_max_func_len(raw: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse(["--max-func-len", raw])
    assert excinfo.value.code == 2


def test_add_lint_command_parses_max_file_len() -> None:
    assert _parse(["--max-file-len", "500"]).max_file_len == 500


@pytest.mark.parametrize("raw", ["0", "-1", "ten"])
def test_add_lint_command_rejects_bad_max_file_len(raw: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse(["--max-file-len", raw])
    assert excinfo.value.code == 2


def test_add_lint_command_rejects_exclude_with_rule() -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse(["--exclude", "funclen", "--rule", "funclen"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("funclen", frozenset({Rule.FUNCLEN})),
        (" funclen , ,funclen, ", frozenset({Rule.FUNCLEN})),
        ("", frozenset()),
    ],
)
def test_add_lint_command_parses_exclude(raw: str, expected: frozenset[Rule]) -> None:
    assert _parse(["--exclude", raw]).exclude == expected


def test_add_lint_command_parses_rule() -> None:
    assert _parse(["--rule", "funclen"]).rule is Rule.FUNCLEN


@pytest.mark.parametrize("argv", [["--exclude", "funclen,typo"], ["--rule", "typo"]])
def test_add_lint_command_rejects_unknown_rule(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse(argv)
    assert excinfo.value.code == 2


def test_lint_handler_runs_lint(lint_calls: list[LintOptions]) -> None:
    args = _parse(["--paths", "src,tests", "--no-fix"])
    args.handler(args)
    assert lint_calls == [
        LintOptions(paths=["src", "tests"], fix=False, linter_config=_DEFAULT_CONFIG)
    ]


def test_lint_handler_exits_on_lint_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lint, "run_lint", _fail_lint)
    args = _parse([])
    with pytest.raises(SystemExit) as excinfo:
        args.handler(args)
    assert isinstance(excinfo.value.__cause__, LintError)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], _DEFAULT_CONFIG),
        (
            ["--max-func-len", "5", "--max-file-len", "7", "--exclude", "funclen"],
            Config(max_func_len=5, max_file_len=7, exclude=frozenset({Rule.FUNCLEN})),
        ),
    ],
)
def test_lint_options_builds_linter_config(argv: list[str], expected: Config) -> None:
    assert lint._lint_options(_parse(argv)).linter_config == expected


def test_lint_options_excludes_every_other_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lint, "Rule", _TwoRules)
    config = lint._lint_options(_parse(["--rule", "funclen"])).linter_config
    assert {str(rule) for rule in config.exclude} == {"other"}
