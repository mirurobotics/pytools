import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Rule,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import (
    DeclaredName,
    NameKind,
    declared_names,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_at_or_above

_MESSAGE: Final = "mutable global variable: use a Final constant or a function instead"
_DEFS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def check(file: CheckInput) -> list[Diagnostic]:
    """Report module-level variables other than type aliases and Final constants."""
    constants = _constant_names(file.tree)
    diags = [_check_name(file, name, constants) for name in declared_names(file)]
    return [diag for diag in diags if diag is not None]


def _constant_names(tree: ast.Module) -> set[ast.expr]:
    aliases = [node.name for node in ast.walk(tree) if isinstance(node, ast.TypeAlias)]
    return {*aliases, *_final_constants(tree)}


def _final_constants(tree: ast.Module) -> list[ast.Name]:
    """Return the targets of module-level Finals whose values are constant.

    A value may name a constant bound above it, as module code runs in order.
    """
    constants: dict[str, ast.Name] = {}
    for node in walk_outside(tree.body, _DEFS):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if _is_constant(node, set(constants)):
            constants[node.target.id] = node.target
    return list(constants.values())


def _is_constant(stmt: ast.AnnAssign, names: set[str]) -> bool:
    """Report whether stmt declares a constant: a Final that is immutable throughout.

    Anything that holds state, such as a list or a compiled regex, is what a
    function returns instead.
    """
    if stmt.value is None or not _is_final(stmt.annotation):
        return False
    return _is_constant_expr(stmt.value, names)


def _is_final(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "Final"
    return isinstance(annotation, ast.Name) and annotation.id == "Final"


def _is_constant_expr(expr: ast.expr, names: set[str]) -> bool:
    """Report whether expr builds an immutable value from constants.

    Its leaves are literals, names in names and dotted references such as
    re.IGNORECASE; operators, tuples, frozensets and f-strings combine them.
    """
    if isinstance(expr, ast.Name):
        return expr.id in names
    if isinstance(expr, ast.Attribute):
        return _is_dotted(expr)
    if isinstance(expr, ast.Call):
        return _is_frozenset(expr, names)
    parts = _parts(expr)
    return parts is not None and all(_is_constant_expr(part, names) for part in parts)


def _is_dotted(expr: ast.Attribute) -> bool:
    if isinstance(expr.value, ast.Attribute):
        return _is_dotted(expr.value)
    return isinstance(expr.value, ast.Name)


def _is_frozenset(call: ast.Call, names: set[str]) -> bool:
    """Report whether call builds a frozenset of constants.

    The frozenset copies a list or set display, so its items are what count.
    """
    is_frozenset = isinstance(call.func, ast.Name) and call.func.id == "frozenset"
    if not is_frozenset or call.keywords or len(call.args) > 1:
        return False
    items = [
        item
        for arg in call.args
        for item in (arg.elts if isinstance(arg, ast.List | ast.Set) else [arg])
    ]
    return all(_is_constant_expr(item, names) for item in items)


def _parts(expr: ast.expr) -> list[ast.expr] | None:
    """Return the subexpressions expr is constant through, or None if it never is."""
    if isinstance(expr, ast.Constant):
        return []
    if isinstance(expr, ast.UnaryOp):
        return [expr.operand]
    if isinstance(expr, ast.BinOp):
        return [expr.left, expr.right]
    if isinstance(expr, ast.BoolOp | ast.JoinedStr):
        return expr.values
    if isinstance(expr, ast.Tuple):
        return expr.elts
    if isinstance(expr, ast.FormattedValue):
        spec = [expr.format_spec] if expr.format_spec else []
        return [expr.value, *spec]
    return None


def _check_name(
    file: CheckInput, name: DeclaredName, constants: set[ast.expr]
) -> Diagnostic | None:
    if name.kind != NameKind.MODULE_VAR or name.node in constants:
        return None
    if has_nolint_at_or_above(file, Rule.MUTABLEGLOBAL, name.line, name.last_line):
        return None
    return Diagnostic(file.path, name.line, _MESSAGE)
