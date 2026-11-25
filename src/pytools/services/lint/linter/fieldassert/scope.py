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
    declared_names,
    first_bindings,
    own_parts,
)

_PURE_BUILTINS: Final = frozenset(
    {"len", "min", "max", "bool", "int", "float", "complex", "str", "bytes"}
)
_NAMED: Final = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.ExceptHandler,
    ast.MatchAs,
    ast.MatchStar,
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
    imports: frozenset[str]  # the module's, or the class body's around the block
    pure_builtins: frozenset[str]  # those no name in the file rebinds

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


def class_imports(
    file: CheckInput, cls: ast.ClassDef, outer: frozenset[str]
) -> frozenset[str]:
    """Return the imports cls's body sees: its own, and outer ones it doesn't bind."""
    bound = frozenset(name.text for name in first_bindings(file, cls))
    return (outer - bound) | import_names(cls.body)


def pure_builtins(file: CheckInput) -> frozenset[str]:
    """Return the pure builtins, such as len, that no name in file rebinds."""
    imports = [
        node
        for node in ast.walk(file.tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]
    bound = {name.text for name in declared_names(file)} | import_names(imports)
    return _PURE_BUILTINS - bound


def import_names(nodes: Iterable[ast.AST]) -> frozenset[str]:
    """Return the names imports among nodes bind, outside nested scopes."""
    aliases = [
        alias
        for node in walk_outside(nodes, SCOPES)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ]
    return frozenset(_alias_name(alias) for alias in aliases)


def changed_names(node: ast.AST, pure: frozenset[str]) -> frozenset[str]:
    """Return the names node may change.

    An assert or expression changes only the names under a call, lambda or
    walrus in it, except a call to a pure builtin; any other statement may
    change every name it uses. An assert's message runs only when it fails.
    """
    test = node.test if isinstance(node, ast.Assert) else node
    if not isinstance(test, ast.stmt):
        changing = [child for child in ast.walk(test) if _may_change(child, pure)]
    else:
        changing = [test]
    return frozenset(name for child in changing for name in name_set(child))


def _may_change(node: ast.AST, pure: frozenset[str]) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        return not (isinstance(func, ast.Name) and func.id in pure)
    return isinstance(node, ast.Lambda | ast.NamedExpr)


def name_set(node: ast.AST) -> frozenset[str]:
    """Return the names node reads or binds; attribute names are not names."""
    return frozenset(name for child in ast.walk(node) for name in _own_names(child))


def _own_names(node: ast.AST) -> list[str]:
    """Return the names node itself reads or binds, such as an except alias."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.alias):
        return [_alias_name(node)]
    if isinstance(node, _NAMED) and node.name:
        return [node.name]
    if isinstance(node, ast.MatchMapping) and node.rest:
        return [node.rest]
    return []


def _alias_name(alias: ast.alias) -> str:
    return alias.asname or alias.name.split(".")[0]


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
