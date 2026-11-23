import ast
import sys
from pathlib import Path

from pytools.services.lint.linter.rules import CheckInput, Config, run_checks


def run_linter(path: str, config: Config) -> int:
    """Lint the Python files under path, print each diagnostic and return the count."""
    return sum(_process_file(file, config) for file in _find_python_files(Path(path)))


def _find_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    files: list[Path] = []
    for directory, subdirs, names in root.walk():
        subdirs[:] = [name for name in subdirs if not name.startswith(".")]
        files.extend(directory / name for name in names if name.endswith(".py"))
    return sorted(files)


def _process_file(path: Path, config: Config) -> int:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as err:
        sys.stderr.write(f"warning: {path}: {err}\n")
        return 0
    diags = run_checks(CheckInput(str(path), tree, source), config)
    for diag in diags:
        sys.stdout.write(f"{diag}\n")
    return len(diags)
