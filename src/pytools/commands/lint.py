from __future__ import annotations

import argparse

from pytools.services.lint.lint import LintError, LintOptions, run_lint

_DESCRIPTION = (
    "Run the full Python lint suite: ruff format, ruff check and mypy. "
    "By default, runs in fix mode. Use --fix=false for CI (check-only) mode."
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
        type=_parse_bool,
        nargs="?",
        const=True,
        default=True,
        help="auto-fix violations (false for CI check-only mode)",
    )


def _parse_paths(raw: str) -> list[str]:
    paths = [path.strip() for path in raw.split(",") if path.strip()]
    if not paths:
        raise argparse.ArgumentTypeError("expected at least one path")
    return paths


def _parse_bool(raw: str) -> bool:
    if raw not in ("true", "false"):
        raise argparse.ArgumentTypeError(f"expected true or false, got {raw!r}")
    return raw == "true"


def _run(args: argparse.Namespace) -> None:
    opts = LintOptions(paths=args.paths, fix=args.fix)
    try:
        run_lint(opts)
    except LintError as err:
        raise SystemExit(str(err)) from err
