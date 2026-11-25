import ast
import re
from pathlib import Path
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
)

_DELIMITERS: Final = r"^[A-Za-z]*(\"\"\"|'''|\"|')|(\"\"\"|'''|\"|')$"


def check(file: CheckInput, max_lines: int, max_package_lines: int) -> list[Diagnostic]:
    """Report docstrings over max_lines, or a package docstring over its own limit."""
    is_package = Path(file.path).name == "__init__.py"
    module_limit = max_package_lines if is_package else max_lines
    owners = [
        node
        for node in ast.walk(file.tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    diags = [_check_docstring(file, file.tree, module_limit)]
    diags += [_check_docstring(file, owner, max_lines) for owner in owners]
    found = [diag for diag in diags if diag is not None]
    return sorted(found, key=lambda diag: diag.line)


def _check_docstring(
    file: CheckInput, owner: ast.Module | Function | ast.ClassDef, limit: int
) -> Diagnostic | None:
    first = owner.body[0] if owner.body else None
    if not isinstance(first, ast.Expr) or ast.get_docstring(owner) is None:
        return None
    count = _count_lines(file, first.value)
    if count <= limit:
        return None
    message = f"docstring is {count} lines (limit {limit})"
    return Diagnostic(file.path, first.value.lineno, message)


def _count_lines(file: CheckInput, doc: ast.expr) -> int:
    lines = file.lines[doc.lineno - 1 : doc.end_lineno or doc.lineno]
    lines[-1] = lines[-1].encode()[: doc.end_col_offset].decode()
    lines[0] = lines[0].encode()[doc.col_offset :].decode()
    text = re.sub(_DELIMITERS, "", "\n".join(lines))
    prose = [index for index, line in enumerate(text.split("\n")) if line.strip()]
    return prose[-1] - prose[0] + 1 if prose else 0
