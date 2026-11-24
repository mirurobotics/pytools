import ast
import shutil
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.analysis.comments import collect_comments
from pytools.services.lint.linter.rules import Config, run_checks, run_fixes


def run_linter(files: list[str], config: Config) -> int:
    """Lint each file, print each diagnostic and return the count."""
    return sum(_process_file(Path(file), config) for file in files)


def _process_file(path: Path, config: Config) -> int:
    file = _read(path)
    if file is None:
        return 0
    diags = run_checks(file, config)
    for diag in diags:
        sys.stdout.write(f"{diag}\n")
    return len(diags)


def run_fixer(files: list[str], config: Config) -> None:
    """Rewrite each file the rules' fixes change."""
    for file in files:
        _fix_file(Path(file), config)


def _fix_file(path: Path, config: Config) -> None:
    file = _read(path)
    if file is None:
        return
    fixed = run_fixes(file, config)
    if fixed is not None:
        _write(path, fixed)


def _read(path: Path) -> CheckInput | None:
    """Return path parsed, or None after a warning if it can't be read or parsed."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as err:
        _warn(path, err)
        return None
    return CheckInput(str(path), tree, source.split("\n"), collect_comments(source))


def _write(path: Path, source: str) -> None:
    """Replace path's content with source in one step, keeping its mode.

    On failure it warns and leaves the file as it was.
    """
    prefix = f".{path.name}."
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=prefix, delete_on_close=False
        ) as temp:
            temp.write(source)
            temp.close()
            shutil.copymode(path, temp.name)
            Path(temp.name).replace(path)
    except OSError as err:
        _warn(path, err)


def _warn(path: Path, err: Exception) -> None:
    sys.stderr.write(f"warning: {path}: {err}\n")
