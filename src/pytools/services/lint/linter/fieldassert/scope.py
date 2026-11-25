import ast
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    is_test_func,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import (
    SCOPES,
    first_bindings,
    own_parts,
)

_PURE_BUILTINS: Final = frozenset(
    {"len", "min", "max", "bool", "int", "float", "complex", "str", "bytes"}
)


@dataclass(frozen=True)
class FuncScope:
    """A def, the names that bind in it and which are parameters or imports."""

    func: Function
    bound: frozenset[str]
    params: frozenset[str]
    imports: frozenset[str]


@dataclass(frozen=True)
class Bindings:
    """Where the names in one block of statements are bound."""

    scopes: tuple[FuncScope, ...]  # the defs around the block, innermost last
    imports: frozenset[str]  # the module's own

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
        owner = self._owner(expr.id)
        return expr.id in (self.imports if owner is None else owner.imports)

    def _owner(self, name: str) -> FuncScope | None:
        owners = (scope for scope in reversed(self.scopes) if name in scope.bound)
        return next(owners, None)


def new_func_scope(file: CheckInput, func: Function) -> FuncScope:
    """Return the names that bind in func, its parameters and imports among them."""
    names = first_bindings(file, func)
    params = frozenset(name.text for name in names if isinstance(name.node, ast.arg))
    imports = import_names(own_parts(func))
    bound = frozenset(name.text for name in names) | imports
    return FuncScope(func, bound, params, imports)


def import_names(nodes: Iterable[ast.AST]) -> frozenset[str]:
    """Return the names imports among nodes bind, outside nested scopes."""
    aliases = [
        alias
        for node in walk_outside(nodes, SCOPES)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ]
    return frozenset(alias.asname or alias.name.split(".")[0] for alias in aliases)


def changed_names(node: ast.AST) -> frozenset[str]:
    """Return the names node may change.

    An assert or expression changes only the names under a call, lambda or
    walrus in it, except a call to a pure builtin; any other statement may
    change every name it uses. An assert's message runs only when it fails.
    """
    test = node.test if isinstance(node, ast.Assert) else node
    if not isinstance(test, ast.stmt):
        changing = [child for child in ast.walk(test) if _may_change(child)]
    else:
        changing = [test]
    return frozenset(name for child in changing for name in name_set(child))


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
