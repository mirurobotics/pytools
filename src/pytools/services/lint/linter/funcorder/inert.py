import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import DEFS, Function
from pytools.services.lint.linter.analysis.names import outer_parts, param_defaults

_PLAIN: Final = (ast.Name, ast.Constant)


def is_inert(decl: Function | ast.ClassDef) -> bool:
    """Report whether defining decl surely runs no code.

    A def has no decorators, its defaults are literals, and its annotations are
    literals or names. A class has no decorators, bases or keywords, and its
    body holds only docstrings, `pass`, such defs, and literals bound to names.
    """
    if not isinstance(decl, ast.ClassDef):
        return _is_inert_def(decl)
    if decl.decorator_list or decl.bases or decl.keywords:
        return False
    return all(_is_inert_stmt(stmt) for stmt in decl.body)


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
        return _is_inert_def(stmt)
    return isinstance(stmt, ast.Pass)


def _is_inert_def(func: Function) -> bool:
    defaults = param_defaults(func.args)
    annotations = [part for part in outer_parts(func) if part not in defaults]
    is_literal = all(isinstance(default, ast.Constant) for default in defaults)
    is_plain = all(isinstance(part, _PLAIN) for part in annotations)
    return not func.decorator_list and is_literal and is_plain
