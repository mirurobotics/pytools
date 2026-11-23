import ast
import sys
from pathlib import Path

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.analysis.comments import collect_comments
from pytools.services.lint.linter.rules import Config, run_checks


def run_linter(files: list[str], config: Config) -> int:
    """Lint each file, print each diagnostic and return the count."""
    return sum(_process_file(Path(file), config) for file in files)


def _process_file(path: Path, config: Config) -> int:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as err:
        sys.stderr.write(f"warning: {path}: {err}\n")
        return 0
    file = CheckInput(str(path), tree, source.split("\n"), collect_comments(source))
    diags = run_checks(file, config)
    for diag in diags:
        sys.stdout.write(f"{diag}\n")
    return len(diags)
