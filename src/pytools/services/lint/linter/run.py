import ast
import sys
from pathlib import Path

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
        path.write_text(fixed, encoding="utf-8")


def _read(path: Path) -> CheckInput | None:
    """Return path parsed, or None after a warning if it can't be read or parsed."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as err:
        sys.stderr.write(f"warning: {path}: {err}\n")
        return None
    return CheckInput(str(path), tree, source.split("\n"), collect_comments(source))
