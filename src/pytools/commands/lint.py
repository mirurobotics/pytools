from __future__ import annotations

import argparse

from pytools.services.lint.lint import LintError, LintOptions, run_lint
from pytools.services.lint.linter.analysis.analysis import Rule
from pytools.services.lint.linter.rules import Config

_DESCRIPTION = (
    "Run the full Python lint suite: ruff check, ruff format, custom linter and "
    "mypy. By default, runs in fix mode. Use --no-fix for CI (check-only) mode."
)


def add_lint_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add the lint command, which runs all Python linters."""
    parser = commands.add_parser(
        "lint", help="Run all Python linters", description=_DESCRIPTION
    )
    _bind_lint_flags(parser)
    parser.set_defaults(handler=_run)


def _bind_lint_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--paths",
        type=_parse_paths,
        default=".",
        help="comma-separated paths to lint",
    )
    parser.add_argument(
        "--fix",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="auto-fix violations (--no-fix for CI check-only mode)",
    )
    _bind_linter_config_flags(parser)


def _parse_paths(raw: str) -> list[str]:
    paths = [path.strip() for path in raw.split(",") if path.strip()]
    if not paths:
        raise argparse.ArgumentTypeError("expected at least one path")
    return paths


def _bind_linter_config_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-func-len",
        type=_parse_limit,
        default=30,
        help="maximum function length (code lines; a multi-line literal counts once)",
    )
    parser.add_argument(
        "--max-file-len",
        type=_parse_limit,
        default=300,
        help="maximum file length (non-blank, non-comment)",
    )
    parser.add_argument(
        "--max-nest-depth",
        type=_parse_limit,
        default=2,
        help="maximum nesting depth within functions",
    )
    rules = parser.add_mutually_exclusive_group()
    rules.add_argument(
        "--exclude",
        type=_parse_rules,
        default=frozenset(),
        help="comma-separated rules to exclude",
    )
    rules.add_argument("--rule", type=_parse_rule, help="only run a specific rule")


def _parse_limit(raw: str) -> int:
    try:
        limit = int(raw)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}") from err
    if limit <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive limit, got {limit}")
    return limit


def _parse_rules(raw: str) -> frozenset[Rule]:
    return frozenset(
        _parse_rule(name.strip()) for name in raw.split(",") if name.strip()
    )


def _parse_rule(raw: str) -> Rule:
    try:
        return Rule(raw)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"unknown lint rule: {raw!r}") from err


def _run(args: argparse.Namespace) -> None:
    try:
        run_lint(_lint_options(args))
    except LintError as err:
        raise SystemExit(str(err)) from err


def _lint_options(args: argparse.Namespace) -> LintOptions:
    exclude = args.exclude if args.rule is None else frozenset(Rule) - {args.rule}
    config = Config(
        max_func_len=args.max_func_len,
        max_file_len=args.max_file_len,
        max_nest_depth=args.max_nest_depth,
        exclude=exclude,
    )
    return LintOptions(paths=args.paths, fix=args.fix, linter_config=config)
