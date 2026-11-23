import subprocess
import sys
from importlib.resources import as_file, files
from pathlib import Path

_CONFIG_DIR = files("pytools.services.lint")


def list_python_files(paths: list[str]) -> list[str]:
    """List the .py files under paths that ruff lints, relative to the working dir."""
    with as_file(_CONFIG_DIR / "ruff.toml") as config:
        args = ["check", "--show-files", "--config", str(config), *paths]
        listed = subprocess.run(  # noqa: S603
            _command("ruff", args), capture_output=True, text=True, check=True
        )
    listed_files = (Path(line) for line in listed.stdout.splitlines())
    return [
        str(file.relative_to(Path.cwd(), walk_up=True))
        for file in listed_files
        if file.suffix == ".py"
    ]


def run_ruff_format(paths: list[str], *, fix: bool) -> bool:
    """Run ruff format (check only unless fix); return whether it passed."""
    return _run_ruff(["format"] if fix else ["format", "--check"], paths)


def run_ruff_check(paths: list[str], *, fix: bool) -> bool:
    """Run ruff check, applying fixes when fix is true; return whether it passed."""
    return _run_ruff(["check", "--fix"] if fix else ["check"], paths)


def _run_ruff(args: list[str], paths: list[str]) -> bool:
    with as_file(_CONFIG_DIR / "ruff.toml") as config:
        return _run_tool("ruff", [*args, "--config", str(config), *paths])


def run_mypy(paths: list[str]) -> bool:
    """Run mypy with the shared strict config; return whether it passed."""
    with as_file(_CONFIG_DIR / "mypy.ini") as config:
        return _run_tool("mypy", ["--config-file", str(config), *paths])


def _run_tool(module: str, args: list[str]) -> bool:
    command = _command(module, args)
    return subprocess.run(command, check=False).returncode == 0  # noqa: S603


def _command(module: str, args: list[str]) -> list[str]:
    return [sys.executable, "-m", module, *args]
