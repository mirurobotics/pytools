import ast
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
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
_COMPOUND: Final = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.Match,
    ast.With,
    ast.AsyncWith,
)

type _Root = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
type _Comp = ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
type _Hidden = tuple[dict[str, int], int, frozenset[str]]


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
    if not isinstance(stmt, DEFS):
        return []
    receiver = _receiver(stmt)
    own = [
        node
        for node, bound in _scoped_nodes(file, stmt)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == receiver
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
    loads = [
        node
        for node, bound in _scoped_nodes(file, root)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in bound
        and node.id not in params
    ]
    return [name.id for name in sorted(loads, key=_position)]


def _scoped_nodes(
    file: CheckInput, root: _Root
) -> list[tuple[ast.AST, frozenset[str]]]:
    """Return the nodes that run when root is called, with the names bound there.

    A name bound in a scope hides a def in that scope and the scopes nested in
    it, but a class body's names don't reach its methods, and a global name
    hides nothing. Root's own parameters are left out. A stack, not recursion,
    so deep nesting doesn't overflow.
    """
    body: list[ast.AST] = [root.body] if isinstance(root, ast.Lambda) else [*root.body]
    pending: list[tuple[list[ast.AST], frozenset[str], bool]] = [
        (body, frozenset(), False)
    ]
    found: list[tuple[ast.AST, frozenset[str]]] = []
    while pending:
        parts, outer, is_class = pending.pop()
        nodes = _run_nodes(parts)
        global_names = _declared(nodes, ast.Global)
        bound = (outer - global_names) | _bound_names(file, nodes)
        inner = outer if is_class else bound
        scopes = [node for node in nodes if isinstance(node, SCOPES)]
        pending.extend(
            (_inner_parts(scope), inner, isinstance(scope, ast.ClassDef))
            for scope in scopes
        )
        found.extend((node, bound) for node in nodes)
    return found


def _position(node: ast.expr) -> tuple[int, int]:
    return node.lineno, node.col_offset


def import_time_names(file: CheckInput, stmt: ast.stmt) -> set[str]:
    """Return the names stmt loads outside function and lambda bodies.

    A def's outer parts run before its name is bound, so its own name there is
    the def it replaces, such as the getter in a property's setter decorator. A
    stack, not recursion, so deep nesting doesn't overflow.
    """
    own = stmt.name if isinstance(stmt, DEFS) else ""
    pending: list[tuple[ast.AST, _Hidden]] = [(stmt, ({}, 0, frozenset()))]
    names: set[str] = set()
    while pending:
        node, hidden = pending.pop()
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id != own
            and not _is_hidden(hidden, node.id)
        ):
            names.add(node.id)
        pending.extend(_import_time_parts(file, node, hidden))
    return names


def _is_hidden(hidden: _Hidden, name: str) -> bool:
    bound, idx, local = hidden
    return name in local or bound.get(name, idx) < idx


def _import_time_parts(
    file: CheckInput, node: ast.AST, hidden: _Hidden
) -> list[tuple[ast.AST, _Hidden]]:
    """Return the parts of node that run when it does, with the names they hide.

    A name a class body binds hides the module's in later statements of that
    body, but not in its comprehensions past their first iterable. There, the
    targets of that comprehension and those around it hide names instead.
    """
    if isinstance(node, _ROOTS):
        return [(part, hidden) for part in outer_parts(node)]
    if isinstance(node, _COMPS):
        first = node.generators[0].iter
        local = hidden[2] | _bound_names(file, _run_nodes(own_parts(node)))
        rest: list[tuple[ast.AST, _Hidden]] = [
            (part, ({}, 0, local)) for part in _inner_parts(node)
        ]
        return [(first, hidden), *rest]
    if not isinstance(node, ast.ClassDef):
        return [(part, hidden) for part in ast.iter_child_nodes(node)]
    bound = _class_bindings(file, node)
    outer = [(part, hidden) for part in outer_parts(node)]
    body = enumerate(node.body)
    return [*outer, *((part, (bound, idx, frozenset())) for idx, part in body)]


def _inner_parts(scope: _Root | ast.ClassDef | _Comp) -> list[ast.AST]:
    """Return the parts of scope that run in it.

    A comprehension's first iterable runs in the scope around it instead.
    """
    if not isinstance(scope, _COMPS):
        return own_parts(scope)
    first = scope.generators[0].iter
    inner = [part for part in outer_parts(scope) if part is not first]
    return [*own_parts(scope), *inner]


def _class_bindings(file: CheckInput, cls: ast.ClassDef) -> dict[str, int]:
    """Return the first statement of cls's body that surely binds each name."""
    body = list(enumerate(cls.body))
    return {
        name: idx
        for idx, stmt in reversed(body)
        if _is_definite(stmt)
        for name in bound_names(file, stmt)
    }


def _is_definite(stmt: ast.stmt) -> bool:
    """Report whether stmt surely binds the names it binds once it runs.

    An annotation without a value binds nothing, and a compound statement may
    skip the statements under it.
    """
    is_annotation = isinstance(stmt, ast.AnnAssign) and stmt.value is None
    return not is_annotation and not isinstance(stmt, _COMPOUND)


def bound_names(file: CheckInput, stmt: ast.stmt) -> frozenset[str]:
    """Return the names stmt binds in the scope it runs in."""
    return _bound_names(file, _run_nodes([stmt]))


def _bound_names(file: CheckInput, nodes: list[ast.AST]) -> frozenset[str]:
    """Return the names nodes bind, which hide a def of the same name.

    An import binds a name too, and a global or nonlocal name binds elsewhere.
    """
    found = [binding(file, node, NameKind.LOCAL_VAR) for node in nodes]
    aliases = [node for node in nodes if isinstance(node, ast.alias)]
    imported = [alias.asname or alias.name.partition(".")[0] for alias in aliases]
    names = {*imported, *(name.text for name in found if name is not None)}
    declared = _declared(nodes, ast.Global) | _declared(nodes, ast.Nonlocal)
    return frozenset(names - declared)


def _declared(nodes: list[ast.AST], kind: type[ast.Global | ast.Nonlocal]) -> set[str]:
    return {name for node in nodes if isinstance(node, kind) for name in node.names}


def _run_nodes(parts: list[ast.AST]) -> list[ast.AST]:
    """Return parts and the nodes under them that run in the same scope.

    A nested scope adds only its outer parts, such as decorators and defaults.
    A comprehension adds its first iterable and its walrus targets, which bind
    in the scope around it.
    """
    pending = list(parts)
    nodes: list[ast.AST] = []
    while pending:
        node = pending.pop()
        nodes.append(node)
        if isinstance(node, ast.arg):
            continue
        if isinstance(node, _COMPS):
            pending.extend(_comp_outer_parts(node))
        elif isinstance(node, SCOPES):
            pending.extend(outer_parts(node))
        else:
            pending.extend(ast.iter_child_nodes(node))
    return nodes


def _comp_outer_parts(comp: _Comp) -> list[ast.AST]:
    nodes = walk_outside([comp], (*_ROOTS, ast.ClassDef))
    targets = [node.target for node in nodes if isinstance(node, ast.NamedExpr)]
    return [comp.generators[0].iter, *targets]
