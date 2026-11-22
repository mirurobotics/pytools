import argparse

from pytools.commands.lint import add_lint_command


def run(argv: list[str]) -> None:
    """Parse argv and run the chosen pytools command."""
    args = _new_parser().parse_args(argv)
    args.handler(args)


def _new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pytools",
        description="A collection of Python development tools for Miru projects.",
    )
    commands = parser.add_subparsers(required=True)
    add_lint_command(commands)
    return parser
