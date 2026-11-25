import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import DEFS, Function
from pytools.services.lint.linter.analysis.names import outer_parts, param_defaults

_PLAIN: Final = (ast.Name, ast.Constant)
_RUNS: Final = (
    ast.Call,
    ast.NamedExpr,
    ast.Lambda,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
_PURE: Final = frozenset(
    {
        "abc.abstractmethod",
        "classmethod",
        "dataclasses.dataclass",
        "enum.unique",
        "functools.cache",
        "functools.cached_property",
        "functools.lru_cache",
        "functools.singledispatch",
        "functools.total_ordering",
        "functools.wraps",
        "property",
        "staticmethod",
        "typing.final",
        "typing.overload",
        "typing.override",
        "typing.runtime_checkable",
    }
)


def is_inert(decl: Function | ast.ClassDef) -> bool:
    """Report whether defining decl surely runs no code."""
    if not isinstance(decl, ast.ClassDef):
        return _is_inert_def(decl)
    if decl.bases or decl.keywords or not _are_pure(decl.decorator_list):
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
        return is_named and is_literal and _is_plain(stmt.annotation)
    if isinstance(stmt, DEFS):
        return _is_inert_def(stmt)
    return isinstance(stmt, ast.Pass)


def _is_inert_def(func: Function) -> bool:
    defaults = param_defaults(func.args)
    skipped = [*defaults, *func.decorator_list]
    hints = [part for part in outer_parts(func) if part not in skipped]
    is_literal = all(isinstance(default, ast.Constant) for default in defaults)
    is_plain = all(_is_plain(hint) for hint in hints)
    return is_literal and is_plain and _are_pure(func.decorator_list)


def _is_plain(hint: ast.AST) -> bool:
    """Report whether evaluating annotation hint runs no call or other code."""
    return not any(isinstance(node, _RUNS) for node in ast.walk(hint))


# Matched by name, not by what the file imports.
def _are_pure(decorators: list[ast.expr]) -> bool:
    """Report whether each of decorators is a stdlib one known to run no code."""
    return all(_is_pure(decorator) for decorator in decorators)


def _is_pure(decorator: ast.expr) -> bool:
    target = decorator
    if isinstance(decorator, ast.Call):
        args = [*decorator.args, *(keyword.value for keyword in decorator.keywords)]
        if not all(isinstance(arg, _PLAIN) for arg in args):
            return False
        target = decorator.func
    attrs: list[str] = []
    while isinstance(target, ast.Attribute):
        attrs.append(target.attr)
        target = target.value
    if not isinstance(target, ast.Name):
        return False
    name = ".".join([target.id, *reversed(attrs)])
    return name in _PURE or any(pure.endswith(f".{name}") for pure in _PURE)
