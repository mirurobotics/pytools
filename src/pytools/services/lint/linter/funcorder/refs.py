import ast
from collections.abc import Iterable
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import NameKind, binding, outer_parts

_ROOTS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

type _Root = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


def called_names(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stmt: Function | ast.ClassDef
) -> list[str]:
    """Return the names stmt calls, in order, in code that runs only when called.

    A method calls its class's methods only through its receiver.
    """
    if isinstance(scope, ast.ClassDef):
        return _receiver_calls(file, stmt)
    return _free_calls(file, stmt)


def _receiver_calls(file: CheckInput, stmt: Function | ast.ClassDef) -> list[str]:
    if isinstance(stmt, ast.ClassDef):
        return []
    receiver = _receiver(stmt)
    nodes = _body_nodes(stmt)
    if receiver is None or receiver in _bound_names(file, nodes):
        return []
    attrs = [node for node in nodes if isinstance(node, ast.Attribute)]
    own = [
        attr
        for attr in attrs
        if isinstance(attr.value, ast.Name) and attr.value.id == receiver
    ]
    return [attr.attr for attr in sorted(own, key=_position)]


def _receiver(func: Function) -> str | None:
    params = [*func.args.posonlyargs, *func.args.args]
    is_static = any(
        isinstance(dec, ast.Name) and dec.id == "staticmethod"
        for dec in func.decorator_list
    )
    return None if is_static or not params else params[0].arg


def _free_calls(file: CheckInput, stmt: Function | ast.ClassDef) -> list[str]:
    """Return the names stmt refers to in code that runs only when called."""
    nodes = walk_outside([stmt], _ROOTS)
    roots = [node for node in nodes if isinstance(node, _ROOTS)]
    return [name for root in roots for name in _root_free_calls(file, root)]


def _root_free_calls(file: CheckInput, root: _Root) -> list[str]:
    nodes = _body_nodes(root)
    bound = _bound_names(file, [*nodes, *ast.walk(root.args)])
    names = [node for node in nodes if isinstance(node, ast.Name)]
    loads = [
        name
        for name in names
        if isinstance(name.ctx, ast.Load) and name.id not in bound
    ]
    return [name.id for name in sorted(loads, key=_position)]


def _body_nodes(root: _Root) -> list[ast.AST]:
    parts: list[ast.AST] = [root.body] if isinstance(root, ast.Lambda) else [*root.body]
    return [node for part in parts for node in ast.walk(part)]


def _bound_names(file: CheckInput, nodes: Iterable[ast.AST]) -> set[str]:
    """Return the names nodes bind, which hide a def of the same name."""
    found = (binding(file, node, NameKind.LOCAL_VAR) for node in nodes)
    return {name.text for name in found if name is not None}


def _position(node: ast.expr) -> tuple[int, int]:
    return node.lineno, node.col_offset


def import_time_names(stmts: list[ast.stmt]) -> set[str]:
    """Return the names stmts load outside function and lambda bodies.

    A stack, not recursion, so deep nesting doesn't overflow.
    """
    pending: list[ast.AST] = list(stmts)
    names: set[str] = set()
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        if isinstance(node, _ROOTS):
            pending.extend(outer_parts(node))
        else:
            pending.extend(ast.iter_child_nodes(node))
    return names
