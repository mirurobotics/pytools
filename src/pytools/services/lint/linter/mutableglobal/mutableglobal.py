import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.names import (
    DeclaredName,
    NameKind,
    declared_names,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_at_or_above

_MESSAGE: Final = (
    "mutable global variable: use a Final constant, a type statement"
    " or a function instead"
)


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
    """Report whether stmt declares a Final set to a constant expression."""
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
    """Report whether expr is written only in syntax that builds no mutable value."""
    pending = [expr]
    while pending:
        parts = _parts(pending.pop())
        if parts is None:
            return False
        pending.extend(parts)
    return True


def _parts(expr: ast.expr) -> list[ast.expr] | None:
    """Return the subexpressions expr is constant through, or None if it never is."""
    if isinstance(expr, ast.Constant | ast.Name):
        return []
    if isinstance(expr, ast.Attribute):
        is_dotted = isinstance(expr.value, ast.Attribute | ast.Name)
        return [expr.value] if is_dotted else None
    if isinstance(expr, ast.Call):
        return _frozenset_items(expr)
    if isinstance(expr, ast.UnaryOp):
        return [expr.operand]
    if isinstance(expr, ast.BinOp):
        return [expr.left, expr.right]
    if isinstance(expr, ast.Compare):
        return [expr.left, *expr.comparators]
    if isinstance(expr, ast.IfExp):
        return [expr.test, expr.body, expr.orelse]
    if isinstance(expr, ast.BoolOp | ast.JoinedStr):
        return expr.values
    if isinstance(expr, ast.Tuple):
        return expr.elts
    if isinstance(expr, ast.FormattedValue):
        spec = [expr.format_spec] if expr.format_spec else []
        return [expr.value, *spec]
    return None


def _frozenset_items(call: ast.Call) -> list[ast.expr] | None:
    """Return the items a frozenset call is built from, or None for any other call."""
    is_frozenset = isinstance(call.func, ast.Name) and call.func.id == "frozenset"
    if not is_frozenset or call.keywords or len(call.args) > 1:
        return None
    return [
        item
        for arg in call.args
        for item in (arg.elts if isinstance(arg, ast.List | ast.Set) else [arg])
    ]


def _check_name(
    file: CheckInput, name: DeclaredName, constants: set[ast.expr]
) -> Diagnostic | None:
    if name.kind != NameKind.MODULE_VAR or name.node in constants:
        return None
    if has_nolint_at_or_above(file, Rule.MUTABLEGLOBAL, name.line, name.last_line):
        return None
    return Diagnostic(file.path, name.line, _MESSAGE)
