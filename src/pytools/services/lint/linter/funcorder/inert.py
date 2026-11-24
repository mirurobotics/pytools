import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import DEFS
from pytools.services.lint.linter.analysis.names import outer_parts, param_defaults

_PLAIN: Final = (ast.Name, ast.Constant)


def is_inert(cls: ast.ClassDef) -> bool:
    """Report whether defining cls surely runs no code.

    It has no decorators, bases or keywords, and its body holds only docstrings,
    `pass`, undecorated defs with literal defaults, and literals bound to names.
    Any annotation is a literal or a name.
    """
    if cls.decorator_list or cls.bases or cls.keywords:
        return False
    return all(_is_inert_stmt(stmt) for stmt in cls.body)


def _is_inert_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Expr):
        return isinstance(stmt.value, ast.Constant)
    if isinstance(stmt, ast.Assign):
        is_named = all(isinstance(target, ast.Name) for target in stmt.targets)
        return is_named and isinstance(stmt.value, ast.Constant)
    if isinstance(stmt, ast.AnnAssign):
        is_named = isinstance(stmt.target, ast.Name)
        is_literal = stmt.value is None or isinstance(stmt.value, ast.Constant)
        is_plain = isinstance(stmt.annotation, _PLAIN)
        return is_named and is_literal and is_plain
    if isinstance(stmt, DEFS):
        defaults = param_defaults(stmt.args)
        annotations = [part for part in outer_parts(stmt) if part not in defaults]
        is_literal = all(isinstance(default, ast.Constant) for default in defaults)
        is_plain = all(isinstance(part, _PLAIN) for part in annotations)
        return not stmt.decorator_list and is_literal and is_plain
    return isinstance(stmt, ast.Pass)
