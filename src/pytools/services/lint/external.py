import subprocess
import sys
from importlib.resources import as_file, files

_CONFIG_DIR = files("pytools.services.lint")


def run_ruff_format(paths: list[str], *, fix: bool) -> None:
    """Run ruff format, or only check formatting when fix is false."""
    _run_ruff(["format"] if fix else ["format", "--check"], paths)


def run_ruff_check(paths: list[str], *, fix: bool) -> None:
    """Run ruff check, applying fixes when fix is true."""
    _run_ruff(["check", "--fix"] if fix else ["check"], paths)


def _run_ruff(args: list[str], paths: list[str]) -> None:
    with as_file(_CONFIG_DIR / "ruff.toml") as config:
        _run_tool("ruff", [*args, "--config", str(config), *paths])


def run_mypy(paths: list[str]) -> None:
    """Run mypy with the shared strict config."""
    with as_file(_CONFIG_DIR / "mypy.ini") as config:
        _run_tool("mypy", ["--config-file", str(config), *paths])


def _run_tool(module: str, args: list[str]) -> None:
    command = [sys.executable, "-m", module, *args]
    subprocess.run(command, check=True)  # noqa: S603
