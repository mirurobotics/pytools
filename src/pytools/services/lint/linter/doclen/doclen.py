import ast
from pathlib import Path

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
)


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
    doc = ast.get_docstring(owner)
    if doc is None:
        return None
    count = len(doc.splitlines())
    if count <= limit:
        return None
    message = f"docstring is {count} lines (limit {limit})"
    return Diagnostic(file.path, owner.body[0].lineno, message)
