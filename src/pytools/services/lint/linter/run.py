import ast
import sys
from pathlib import Path

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.analysis.comments import collect_comments
from pytools.services.lint.linter.rules import Config, run_checks, run_fixes


def run_linter(files: list[str], config: Config, *, fix: bool) -> int:
    """Lint each file, print each diagnostic and return the count.

    With fix, each file is first rewritten with the rules' fixes applied.
    """
    return sum(_process_file(Path(file), config, fix=fix) for file in files)


def _process_file(path: Path, config: Config, *, fix: bool) -> int:
    try:
        file = _parse(path, path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, UnicodeDecodeError) as err:
        sys.stderr.write(f"warning: {path}: {err}\n")
        return 0
    if fix:
        file = _apply_fixes(path, file, config)
    diags = run_checks(file, config)
    for diag in diags:
        sys.stdout.write(f"{diag}\n")
    return len(diags)


def _apply_fixes(path: Path, file: CheckInput, config: Config) -> CheckInput:
    """Write the fixed source to path, parsed first so a broken fix never lands."""
    fixed = run_fixes(file, config)
    if fixed is None:
        return file
    fixed_file = _parse(path, fixed)
    path.write_text(fixed, encoding="utf-8")
    return fixed_file


def _parse(path: Path, source: str) -> CheckInput:
    tree = ast.parse(source, filename=str(path))
    return CheckInput(str(path), tree, source.split("\n"), collect_comments(source))
