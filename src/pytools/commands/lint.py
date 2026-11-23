from __future__ import annotations

import argparse

from pytools.services.lint.config import LinterFlags, build_linter_config
from pytools.services.lint.lint import LintError, LintOptions, run_lint
from pytools.services.lint.linter.rules import UnknownRuleError

_DESCRIPTION = (
    "Run the full Python lint suite: custom linter, ruff check, ruff format and "
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
        type=int,
        default=30,
        help="maximum function length (code lines; a multi-line literal counts once)",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="comma-separated rules to exclude (empty=run all)",
    )
    parser.add_argument("--rule", help="only run a specific rule")


def _run(args: argparse.Namespace) -> None:
    try:
        run_lint(_lint_options(args))
    except (LintError, UnknownRuleError) as err:
        raise SystemExit(str(err)) from err


def _lint_options(args: argparse.Namespace) -> LintOptions:
    flags = LinterFlags(
        max_func_len=args.max_func_len, exclude=args.exclude, rule=args.rule
    )
    return LintOptions(
        paths=args.paths, fix=args.fix, linter_config=build_linter_config(flags)
    )
