import ast
from dataclasses import dataclass
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    is_test_func,
)
from pytools.services.lint.linter.analysis.names import first_bindings

_PURE_BUILTINS: Final = frozenset(
    {"len", "min", "max", "bool", "int", "float", "complex", "str", "bytes"}
)


@dataclass(frozen=True)
class FuncScope:
    """A def, the names that bind in it and which of them are its parameters."""

    func: Function
    bound: frozenset[str]
    params: frozenset[str]


@dataclass(frozen=True)
class Bindings:
    """Where the names in one block of statements are bound."""

    scopes: tuple[FuncScope, ...]  # the defs around the block, innermost last
    imports: frozenset[str]

    def is_helper_param(self, name: str | None) -> bool:
        """Report whether name is a parameter of a def that is not a test.

        Such a def is a check helper that takes the value.
        """
        scope = None if name is None else self._owner(name)
        if scope is None or name not in scope.params:
            return False
        return not is_test_func(scope.func)

    def is_pkg(self, expr: ast.expr) -> bool:
        """Report whether expr is an imported name or a dotted path into one."""
        while isinstance(expr, ast.Attribute):
            expr = expr.value
        if not isinstance(expr, ast.Name):
            return False
        return expr.id in self.imports and self._owner(expr.id) is None

    def _owner(self, name: str) -> FuncScope | None:
        owners = (scope for scope in reversed(self.scopes) if name in scope.bound)
        return next(owners, None)


def new_scope(file: CheckInput, func: Function) -> FuncScope:
    """Return the names that bind in func, its parameters among them."""
    names = first_bindings(file, func)
    params = [name.text for name in names if isinstance(name.node, ast.arg)]
    return FuncScope(func, frozenset(name.text for name in names), frozenset(params))


def import_names(tree: ast.Module) -> frozenset[str]:
    """Return the names any import in tree binds."""
    aliases = [
        alias
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ]
    return frozenset(alias.asname or alias.name.split(".")[0] for alias in aliases)


def changed_names(stmt: ast.stmt) -> frozenset[str]:
    """Return the names stmt may change.

    An assert changes only the names under a call, lambda or walrus in it,
    except a call to a pure builtin; any other statement may change every name
    it uses.
    """
    if isinstance(stmt, ast.Assert):
        changing = [node for node in ast.walk(stmt) if _may_change(node)]
    else:
        changing = [stmt]
    return frozenset(name for node in changing for name in name_set(node))


def _may_change(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        return not (isinstance(func, ast.Name) and func.id in _PURE_BUILTINS)
    return isinstance(node, ast.Lambda | ast.NamedExpr)


def name_set(node: ast.AST) -> frozenset[str]:
    """Return the names node reads or binds; attribute names are not names."""
    return frozenset(
        child.id for child in ast.walk(node) if isinstance(child, ast.Name)
    )


def root_name(expr: ast.expr, bindings: Bindings) -> str | None:
    """Return the variable expr reads from, or None, as for a function's result."""
    while not isinstance(expr, ast.Name):
        receiver = _receiver(expr, bindings)
        if receiver is None:
            return None
        expr = receiver
    return expr.id


def _receiver(expr: ast.expr, bindings: Bindings) -> ast.expr | None:
    """Return the value expr reads from: a base, or a method call's object."""
    if isinstance(expr, ast.Attribute | ast.Subscript):
        return expr.value
    func = expr.func if isinstance(expr, ast.Call) else None
    if not isinstance(func, ast.Attribute):
        return None
    return None if bindings.is_pkg(func.value) else func.value
