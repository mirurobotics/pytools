import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.names import (
    DeclaredName,
    NameKind,
    declared_names,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_at_or_above

_MESSAGE: Final = "mutable global variable: use a Final constant or a function instead"


def check(file: CheckInput) -> list[Diagnostic]:
    """Report module-level variables other than type aliases and Final constants."""
    constants = _constant_names(file.tree)
    diags = [_check_name(file, name, constants) for name in declared_names(file)]
    return [diag for diag in diags if diag is not None]


def _constant_names(tree: ast.Module) -> set[ast.expr]:
    nodes = list(ast.walk(tree))
    aliases = [node.name for node in nodes if isinstance(node, ast.TypeAlias)]
    finals = [
        node.target
        for node in nodes
        if isinstance(node, ast.AnnAssign) and _is_constant(node)
    ]
    return {*aliases, *finals}


def _is_constant(stmt: ast.AnnAssign) -> bool:
    """Report whether stmt declares a Go-style constant.

    Go constants are literals and operators on them; anything else, such as a
    collection or a call, is state that a function returns instead.
    """
    if stmt.value is None or not _is_final(stmt.annotation):
        return False
    return _is_constant_expr(stmt.value)


def _is_final(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "Final"
    return isinstance(annotation, ast.Name) and annotation.id == "Final"


def _is_constant_expr(expr: ast.expr) -> bool:
    if isinstance(expr, ast.UnaryOp):
        return _is_constant_expr(expr.operand)
    if isinstance(expr, ast.BinOp):
        return _is_constant_expr(expr.left) and _is_constant_expr(expr.right)
    return isinstance(expr, ast.Constant)


def _check_name(
    file: CheckInput, name: DeclaredName, constants: set[ast.expr]
) -> Diagnostic | None:
    if name.kind != NameKind.MODULE_VAR or name.node in constants:
        return None
    if has_nolint_at_or_above(file, Rule.MUTABLEGLOBAL, name.line, name.last_line):
        return None
    return Diagnostic(file.path, name.line, _MESSAGE)
