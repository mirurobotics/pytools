import ast
from collections import Counter
from dataclasses import dataclass
from typing import Final, TypeGuard

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    ROOTS,
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
    param_defaults,
)
from pytools.services.lint.linter.funcorder.loaded import loaded_nodes

_COMPS: Final = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_TYPE_PARAMS: Final = (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)

type _Root = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
type _Comp = ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
type _Hidden = tuple[dict[str, int], int, frozenset[str]]


def called_names(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stmt: ast.stmt
) -> list[str]:
    """Return the names stmt calls, in order, in code that runs only when called."""
    if isinstance(scope, ast.ClassDef):
        return _receiver_calls(file, stmt)
    return _free_calls(file, stmt)


def _receiver_calls(file: CheckInput, stmt: ast.stmt) -> list[str]:
    if not isinstance(stmt, DEFS):
        return []
    receiver = _receiver(stmt)
    own = [
        node
        for node, bound in _scoped_nodes(file, stmt, frozenset())
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and isinstance(node.value, ast.Name)
        and node.value.id == receiver
        and receiver not in bound
    ]
    return [attr.attr for attr in sorted(own, key=_position)]


def _receiver(func: Function) -> str | None:
    params = [*func.args.posonlyargs, *func.args.args]
    names = [dec.id for dec in func.decorator_list if isinstance(dec, ast.Name)]
    return None if "staticmethod" in names or not params else params[0].arg


def _free_calls(file: CheckInput, stmt: ast.stmt) -> list[str]:
    """Return the names stmt refers to in code that runs only when called."""
    loads = [
        name
        for root, params in _roots(file, stmt)
        for name in _root_free_loads(file, root, params)
    ]
    return [name.id for name in sorted(loads, key=_position)]


def _roots(file: CheckInput, stmt: ast.stmt) -> list[tuple[_Root, frozenset[str]]]:
    """Return stmt's defs and lambdas outside def bodies, and the names hidden there."""
    pending: list[tuple[ast.AST, frozenset[str]]] = [(stmt, frozenset())]
    found: list[tuple[_Root, frozenset[str]]] = []
    while pending:
        node, params = pending.pop()
        if isinstance(node, ROOTS):
            found.append((node, params))
        pending.extend(_scope_parts(file, node, params))
    return found


def _root_free_loads(
    file: CheckInput, root: _Root, params: frozenset[str]
) -> list[ast.Name]:
    own = _bound_names(file, own_parts(root))
    return [
        node
        for node, bound in _scoped_nodes(file, root, params)
        if _is_load(node) and node.id not in bound and node.id not in own
    ]


def _scoped_nodes(
    file: CheckInput, root: _Root, params: frozenset[str]
) -> list[tuple[ast.AST, frozenset[str]]]:
    """Return the nodes that run when root is called, with the names bound there.

    A scope's names hide those in its nested scopes, but a class body passes on
    only its type parameters, and a global name hides nothing.
    """
    body: list[ast.AST] = [root.body] if isinstance(root, ast.Lambda) else [*root.body]
    todo: list[tuple[list[ast.AST], frozenset[str], ast.AST]] = [(body, params, root)]
    found: list[tuple[ast.AST, frozenset[str]]] = []
    while todo:
        parts, outer, host = todo.pop()
        nodes = _run_nodes(parts)
        global_names = _declared(nodes, ast.Global)
        bound = (outer - global_names) | _bound_names(file, nodes)
        inner = outer | _type_params(host) if isinstance(host, ast.ClassDef) else bound
        nested = [node for node in nodes if isinstance(node, SCOPES)]
        todo.extend((_inner_parts(part), inner, part) for part in nested)
        typed = _typed_outer_nodes(nodes)
        found.extend((node, bound | typed.get(node, frozenset())) for node in nodes)
    return found


def _typed_outer_nodes(nodes: list[ast.AST]) -> dict[ast.AST, frozenset[str]]:
    """Return the nodes of the scopes' outer parts that see their type parameters."""
    typed: dict[ast.AST, frozenset[str]] = {}
    for scope in nodes:
        if isinstance(scope, (*DEFS, ast.ClassDef)):
            inside = set(outer_parts(scope)) - set(_outside_type_params(scope))
            typed.update(dict.fromkeys(_run_nodes(list(inside)), _type_params(scope)))
    return typed


def _position(node: ast.expr) -> tuple[int, int]:
    return node.lineno, node.col_offset


@dataclass(frozen=True)
class ImportTimeNames:
    """The names a statement uses when it runs, outside def bodies."""

    loads: set[str]  # loaded from the scope it's in, outside lambda bodies
    called: set[str]  # used other than by only loading them, or read in a lambda
    stored: set[str]  # a class body's values, which only `__set_name__` may run
    binds: frozenset[str]  # bound, except by import, plus every name it declares global
    reads: set[str]  # read where it runs or in its lambdas, wherever they resolve


def import_time_names(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stmt: ast.stmt
) -> ImportTimeNames:
    """Return the names stmt uses outside function and lambda bodies.

    A def's own name in its outer parts is the def it replaces. In a class scope,
    parts that can't see the scope's names are left out, but for reads and calls.
    """
    own = stmt.name if isinstance(stmt, DEFS) else ""
    is_class = isinstance(scope, ast.ClassDef)
    nodes, loads = _import_time_walk(file, stmt, own, is_class=is_class)
    seen = _import_time_walk(file, stmt, own, is_class=False)[0] if is_class else nodes
    reads = {name for node in [*seen, *_in_lambdas(seen)] for name in _reads(node)}
    assigns = [node for node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign))]
    stored = [node.value for node in assigns if isinstance(node.value, ast.Name)]
    classes = [node for node in nodes if isinstance(node, ast.ClassDef)]
    body = {part for cls in classes for part in _run_nodes(list(cls.body))}
    called = _called(nodes, loaded_nodes(nodes, body) | set(stored))
    bound = [node for node in nodes if not isinstance(node, ast.alias)]
    binds = _bound_names(file, bound) | _declared(list(ast.walk(stmt)), ast.Global)
    loads |= _invoked_lambda_loads(file, nodes)
    return ImportTimeNames(loads, called, {name.id for name in stored}, binds, reads)


def _import_time_walk(
    file: CheckInput, stmt: ast.stmt, own: str, *, is_class: bool
) -> tuple[list[ast.AST], set[str]]:
    """Return the nodes of stmt that run when it does, and the names they load."""
    pending: list[tuple[ast.AST, _Hidden]] = [(stmt, ({}, 0, frozenset()))]
    nodes: list[ast.AST] = []
    loads: set[str] = set()
    while pending:
        node, hidden = pending.pop()
        nodes.append(node)
        reads = [name for name in _reads(node) if name != own]
        loads.update(name for name in reads if not _is_hidden(hidden, name))
        pending.extend(_import_time_parts(file, node, hidden, is_class=is_class))
    return nodes, loads


def _is_hidden(hidden: _Hidden, name: str) -> bool:
    bound, idx, local = hidden
    return name in local or bound.get(name, idx) < idx


def _import_time_parts(
    file: CheckInput, node: ast.AST, hidden: _Hidden, *, is_class: bool
) -> list[tuple[ast.AST, _Hidden]]:
    """Return the parts of node that run when it does, with the names they hide.

    A name a class body binds hides the module's in its later statements, but not
    past a comprehension's first iterable there.
    """
    bound, idx, local = hidden
    parts = _scope_parts(file, node, local)
    if isinstance(node, _COMPS):
        first, *rest = parts
        inner: list[tuple[ast.AST, _Hidden]] = [
            (part, ({}, 0, names)) for part, names in rest if not is_class
        ]
        return [(first[0], hidden), *inner]
    if not isinstance(node, ast.ClassDef):
        return [(part, (bound, idx, names)) for part, names in parts]
    body: dict[ast.AST, int] = {part: pos for pos, part in enumerate(node.body)}
    found = _class_bindings(file, node)
    return [
        (part, (found, body[part], names) if part in body else (bound, idx, names))
        for part, names in parts
        if not (is_class and part in body)
    ]


def _scope_parts(
    file: CheckInput, node: ast.AST, local: frozenset[str]
) -> list[tuple[ast.AST, frozenset[str]]]:
    """Return node's parts outside def bodies, with the names hidden in each.

    A comprehension's targets hide names past its first iterable, and a class's
    or def's type parameters hide names past its decorators and defaults.
    """
    if isinstance(node, _COMPS):
        targets = local | _bound_names(file, _run_nodes(own_parts(node)))
        first = node.generators[0].iter
        return [(first, local), *((part, targets) for part in _inner_parts(node))]
    if not isinstance(node, (*ROOTS, ast.ClassDef)):
        return [(part, local) for part in ast.iter_child_nodes(node)]
    typed = local | _type_params(node)
    outside = _outside_type_params(node)
    outer = [(part, local if part in outside else typed) for part in outer_parts(node)]
    body = node.body if isinstance(node, ast.ClassDef) else []
    return [*outer, *((part, typed) for part in body)]


def _inner_parts(scope: _Root | ast.ClassDef | _Comp) -> list[ast.AST]:
    """Return scope's parts that run in it, but a comprehension's first iterable."""
    if not isinstance(scope, _COMPS):
        return own_parts(scope)
    first = scope.generators[0].iter
    inner = [part for part in outer_parts(scope) if part is not first]
    return [*own_parts(scope), *inner]


def _type_params(node: _Root | ast.ClassDef) -> frozenset[str]:
    if isinstance(node, ast.Lambda):
        return frozenset()
    params = node.type_params
    return frozenset(param.name for param in params if isinstance(param, _TYPE_PARAMS))


def _outside_type_params(node: _Root | ast.ClassDef) -> list[ast.AST]:
    """Return node's decorators and defaults, which run outside its type parameters."""
    defaults = [] if isinstance(node, ast.ClassDef) else param_defaults(node.args)
    decorators = [] if isinstance(node, ast.Lambda) else node.decorator_list
    return [*decorators, *defaults]


def _class_bindings(file: CheckInput, cls: ast.ClassDef) -> dict[str, int]:
    """Return where cls's body first surely binds each name it never deletes."""
    deleted = _deleted(_run_nodes(list(cls.body)))
    body = list(enumerate(cls.body))
    return {
        name: idx
        for idx, stmt in reversed(body)
        if _is_definite(stmt)
        for name in bound_names(file, stmt) - deleted
    }


def _is_definite(stmt: ast.stmt) -> bool:
    """Report whether stmt surely binds; a bare annotation, branch or walrus may not."""
    is_annotation = isinstance(stmt, ast.AnnAssign) and stmt.value is None
    nested = _run_nodes([stmt])[1:]
    is_unsure = any(isinstance(node, (ast.NamedExpr, ast.stmt)) for node in nested)
    return not (is_annotation or is_unsure)


def _called(nodes: list[ast.AST], loaded: set[ast.AST]) -> set[str]:
    """Return the names nodes use other than by only loading them, or a lambda reads."""
    used = [node for node in nodes if node not in loaded]
    return {name for node in [*used, *_in_lambdas(nodes)] for name in _reads(node)}


def _in_lambdas(nodes: list[ast.AST]) -> list[ast.AST]:
    lambdas = [node for node in nodes if isinstance(node, ast.Lambda)]
    return [node for lam in lambdas for node in ast.walk(lam.body)]


def _reads(node: ast.AST) -> list[str]:
    """Return the names node reads, such as an augmented assignment's target."""
    if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return [node.id] if _is_load(node) else []


def _invoked_lambda_loads(file: CheckInput, nodes: list[ast.AST]) -> set[str]:
    funcs = {node.func for node in nodes if isinstance(node, ast.Call)}
    lambdas = [node for node in nodes if node in funcs and isinstance(node, ast.Lambda)]
    return {name for lam in lambdas for name in _lambda_loads(file, lam)}


def _lambda_loads(file: CheckInput, lam: ast.Lambda) -> set[str]:
    loads = {node.id for node in ast.walk(lam.body) if _is_load(node)}
    return loads - _bound_names(file, own_parts(lam))


def _is_load(node: ast.AST) -> TypeGuard[ast.Name]:
    return isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)


def scope_bindings(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Counter[str]:
    """Return how many times scope may bind each name, outer and `*` names included."""
    counts = Counter(name for stmt in scope.body for name in bound_names(file, stmt))
    nodes = [node for stmt in scope.body for node in ast.walk(stmt)]
    counts.update(_declared(nodes, ast.Global) | _declared(nodes, ast.Nonlocal))
    return counts


def bound_names(file: CheckInput, stmt: ast.stmt) -> frozenset[str]:
    """Return the names stmt binds or deletes in the scope it runs in."""
    return _bound_names(file, _run_nodes([stmt]))


def _bound_names(file: CheckInput, nodes: list[ast.AST]) -> frozenset[str]:
    """Return the names nodes bind or delete; global or nonlocal ones bind elsewhere."""
    found = [binding(file, node, NameKind.LOCAL_VAR) for node in nodes]
    aliases = [node for node in nodes if isinstance(node, ast.alias)]
    imported = [alias.asname or alias.name.partition(".")[0] for alias in aliases]
    names = {*imported, *(name.text for name in found if name is not None)}
    names.update(_deleted(nodes))
    declared = _declared(nodes, ast.Global) | _declared(nodes, ast.Nonlocal)
    return frozenset(names - declared)


def _deleted(nodes: list[ast.AST]) -> frozenset[str]:
    """Return the names nodes delete, as `del` and an except alias's end do."""
    names = [node for node in nodes if isinstance(node, ast.Name)]
    handlers = [node for node in nodes if isinstance(node, ast.ExceptHandler)]
    aliases = [handler.name for handler in handlers if handler.name]
    deleted = [name.id for name in names if isinstance(name.ctx, ast.Del)]
    return frozenset([*aliases, *deleted])


def _declared(nodes: list[ast.AST], kind: type[ast.Global | ast.Nonlocal]) -> set[str]:
    return {name for node in nodes if isinstance(node, kind) for name in node.names}


def _run_nodes(parts: list[ast.AST]) -> list[ast.AST]:
    """Return parts and the nodes under them that run in the same scope.

    A nested scope adds only its outer parts, and a comprehension its first
    iterable and its walrus targets, which bind in the scope around it.
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
    nodes = walk_outside([comp], (*ROOTS, ast.ClassDef))
    targets = [node.target for node in nodes if isinstance(node, ast.NamedExpr)]
    return [comp.generators[0].iter, *targets]
