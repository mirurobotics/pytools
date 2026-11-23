from __future__ import annotations

import argparse

from pytools.services.lint.lint import LintError, LintOptions, run_lint

_DESCRIPTION = (
    "Run the full Python lint suite: ruff format, ruff check and mypy. "
    "By default, runs in fix mode. Use --no-fix for CI (check-only) mode."
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


def _parse_paths(raw: str) -> list[str]:
    paths = [path.strip() for path in raw.split(",") if path.strip()]
    if not paths:
        raise argparse.ArgumentTypeError("expected at least one path")
    return paths


def _run(args: argparse.Namespace) -> None:
    opts = LintOptions(paths=args.paths, fix=args.fix)
    try:
        run_lint(opts)
    except LintError as err:
        raise SystemExit(str(err)) from err
