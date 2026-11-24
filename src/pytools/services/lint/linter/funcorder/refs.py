import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import (
    SCOPES,
    NameKind,
    binding,
    outer_parts,
    own_parts,
)

_ROOTS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPS: Final = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

type _Root = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


def called_names(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stmt: ast.stmt
) -> list[str]:
    """Return the names stmt calls, in order, in code that runs only when called.

    A method calls its class's methods only through its receiver.
    """
    if isinstance(scope, ast.ClassDef):
        return _receiver_calls(file, stmt)
    return _free_calls(file, stmt)


def _receiver_calls(file: CheckInput, stmt: ast.stmt) -> list[str]:
    if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        return []
    receiver = _receiver(stmt)
    attrs = [
        (node, bound)
        for node, bound in _scoped_nodes(file, stmt)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    ]
    own = [
        attr
        for attr, bound in attrs
        if isinstance(attr.value, ast.Name)
        and attr.value.id == receiver
        and receiver not in bound
    ]
    return [attr.attr for attr in sorted(own, key=_position)]


def _receiver(func: Function) -> str | None:
    params = [*func.args.posonlyargs, *func.args.args]
    is_static = any(
        isinstance(dec, ast.Name) and dec.id == "staticmethod"
        for dec in func.decorator_list
    )
    return None if is_static or not params else params[0].arg


def _free_calls(file: CheckInput, stmt: ast.stmt) -> list[str]:
    """Return the names stmt refers to in code that runs only when called."""
    nodes = walk_outside([stmt], _ROOTS)
    roots = [node for node in nodes if isinstance(node, _ROOTS)]
    return [name for root in roots for name in _root_free_calls(file, root)]


def _root_free_calls(file: CheckInput, root: _Root) -> list[str]:
    params = _bound_names(file, own_parts(root))
    names = [
        (node, bound)
        for node, bound in _scoped_nodes(file, root)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    ]
    loads = [
        name
        for name, bound in names
        if name.id not in bound and name.id not in params
    ]
    return [name.id for name in sorted(loads, key=_position)]


def _scoped_nodes(
    file: CheckInput, root: _Root
) -> list[tuple[ast.AST, frozenset[str]]]:
    """Return the nodes that run when root is called, with the names bound there.

    A name bound in a scope hides a def in that scope and the scopes nested in
    it, but a class body's names don't reach its methods. Root's own parameters
    are left out. A stack, not recursion, so deep nesting doesn't overflow.
    """
    body: list[ast.AST] = [root.body] if isinstance(root, ast.Lambda) else [*root.body]
    pending: list[tuple[list[ast.AST], frozenset[str], bool]] = [
        (body, frozenset(), False)
    ]
    found: list[tuple[ast.AST, frozenset[str]]] = []
    while pending:
        parts, outer, is_class = pending.pop()
        nodes = _run_nodes(parts)
        bound = outer | _bound_names(file, nodes)
        inner = outer if is_class else bound
        for scope in [node for node in nodes if isinstance(node, SCOPES)]:
            comp = outer_parts(scope) if isinstance(scope, _COMPS) else []
            scope_parts = [*own_parts(scope), *comp]
            pending.append((scope_parts, inner, isinstance(scope, ast.ClassDef)))
        found.extend((node, bound) for node in nodes)
    return found


def _run_nodes(parts: list[ast.AST]) -> list[ast.AST]:
    """Return parts and the nodes under them that run in the same scope.

    A nested scope adds only its outer parts, such as decorators and defaults.
    """
    pending = list(parts)
    nodes: list[ast.AST] = []
    while pending:
        node = pending.pop()
        nodes.append(node)
        if isinstance(node, (*_COMPS, ast.arg)):
            continue
        if isinstance(node, SCOPES):
            pending.extend(outer_parts(node))
        else:
            pending.extend(ast.iter_child_nodes(node))
    return nodes


def _bound_names(file: CheckInput, nodes: list[ast.AST]) -> frozenset[str]:
    """Return the names nodes bind, which hide a def of the same name.

    An import binds a name too.
    """
    found = [binding(file, node, NameKind.LOCAL_VAR) for node in nodes]
    aliases = [node for node in nodes if isinstance(node, ast.alias)]
    imported = [alias.asname or alias.name.partition(".")[0] for alias in aliases]
    return frozenset([*imported, *(name.text for name in found if name is not None)])


def _position(node: ast.expr) -> tuple[int, int]:
    return node.lineno, node.col_offset


def import_time_names(stmts: list[ast.stmt]) -> set[str]:
    """Return the names stmts load outside function and lambda bodies.

    A def's outer parts run before its name is bound, so its own name there is
    the def it replaces, such as the getter in a property's setter decorator.
    A stack, not recursion, so deep nesting doesn't overflow.
    """
    pending: list[tuple[ast.AST, str]] = [(stmt, "") for stmt in stmts]
    names: set[str] = set()
    while pending:
        node, own = pending.pop()
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id != own
        ):
            names.add(node.id)
        if isinstance(node, _ROOTS):
            skip = own if isinstance(node, ast.Lambda) else node.name
            pending.extend((part, skip) for part in outer_parts(node))
        else:
            pending.extend((child, own) for child in ast.iter_child_nodes(node))
    return names
