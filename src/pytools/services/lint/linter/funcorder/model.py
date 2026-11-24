import ast
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Function,
    Rule,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import NameKind, binding, outer_parts
from pytools.services.lint.linter.analysis.nolint import has_def_nolint

_DEFS: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
_NODES: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_ROOTS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

type _Root = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


@dataclass(frozen=True)
class Node:
    """A def or class in a scope, one of the units the scope is ordered by."""

    idx: int
    stmt: Function | ast.ClassDef
    name: str
    is_public: bool
    exempt: bool


@dataclass(frozen=True)
class Model:
    """The calls between the defs and classes directly in a scope.

    A class counts as one caller, through its methods' calls. Calls out of or
    into an exempt def, and into a def used at import time, are not enforced.
    """

    stmts: list[ast.stmt]
    nodes: dict[int, Node]
    stubs: frozenset[int]  # defs the next def of the same name replaces
    calls: dict[int, list[int]]  # enforced callees, in the order first called
    callers: dict[int, list[int]]  # enforced callers outside the callee's cycle
    cycle_callers: dict[int, list[int]]
    used: frozenset[int]  # defs referenced anywhere in the scope
    waiting: frozenset[int]  # cycle members placed only after a cycle caller


def build(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Model:
    """Return the calls between the defs and classes directly in scope."""
    stubs = _stubs(scope.body)
    nodes = _nodes(file, scope, stubs)
    by_name = {
        node.stmt.name: idx
        for idx, node in nodes.items()
        if not isinstance(node.stmt, ast.ClassDef)
    }
    callees = {idx: _callees(file, scope, node, by_name) for idx, node in nodes.items()}
    pinned = _pinned(scope.body, by_name)
    calls = {
        idx: [callee for callee in found if _is_enforced(nodes, idx, callee, pinned)]
        for idx, found in callees.items()
    }
    comps = _components(callees)
    callers = {idx: _callers_of(calls, comps, idx, in_cycle=False) for idx in nodes}
    cycles = {idx: _callers_of(calls, comps, idx, in_cycle=True) for idx in nodes}
    used = frozenset(pinned.union(*callees.values()))
    waiting = _waiting(nodes, callers, cycles, comps)
    return Model(scope.body, nodes, stubs, calls, callers, cycles, used, waiting)


def _stubs(stmts: list[ast.stmt]) -> frozenset[int]:
    """Return the defs directly followed by a def of the same name.

    Overloads and property getters are one function with the def they precede.
    """
    pairs = enumerate(pairwise(stmts))
    return frozenset(idx for idx, pair in pairs if _is_redefined(*pair))


def _is_redefined(stmt: ast.stmt, after: ast.stmt) -> bool:
    if not isinstance(stmt, _DEFS) or not isinstance(after, _DEFS):
        return False
    return stmt.name == after.name


def _nodes(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stubs: frozenset[int]
) -> dict[int, Node]:
    prefix = f"{scope.name}." if isinstance(scope, ast.ClassDef) else ""
    return {
        idx: _node(file, idx, stmt, prefix)
        for idx, stmt in enumerate(scope.body)
        if isinstance(stmt, _NODES) and idx not in stubs
    }


def _node(
    file: CheckInput, idx: int, stmt: Function | ast.ClassDef, prefix: str
) -> Node:
    is_def = not isinstance(stmt, ast.ClassDef)
    exempt = is_def and has_def_nolint(file, stmt, Rule.FUNCORDER)
    return Node(idx, stmt, prefix + stmt.name, _is_public(stmt.name), exempt)


def _is_public(name: str) -> bool:
    """Report whether name is public; a dunder is Python's entry point."""
    is_dunder = name.startswith("__") and name.endswith("__")
    return is_dunder or not name.startswith("_")


def _callees(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    node: Node,
    by_name: dict[str, int],
) -> list[int]:
    """Return the defs node calls, in the order it first calls them.

    A method calls its class's methods only through its receiver.
    """
    if isinstance(scope, ast.ClassDef):
        names = _receiver_calls(file, node.stmt)
    else:
        names = _free_calls(file, node.stmt)
    found = [by_name[name] for name in names if name in by_name]
    return [idx for idx in dict.fromkeys(found) if idx != node.idx]


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


def _pinned(stmts: list[ast.stmt], by_name: dict[str, int]) -> set[int]:
    """Return the defs stmts use at import time, which must stay above that use."""
    return {by_name[name] for name in _import_time_names(stmts) if name in by_name}


def _import_time_names(stmts: list[ast.stmt]) -> set[str]:
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


def _is_enforced(
    nodes: dict[int, Node], caller: int, callee: int, pinned: set[int]
) -> bool:
    is_exempt = nodes[caller].exempt or nodes[callee].exempt
    return not is_exempt and callee not in pinned


def _components(callees: dict[int, list[int]]) -> dict[int, int]:
    """Label each def with its cycle's first member, or itself outside a cycle."""
    reach = {idx: _reachable(callees, idx) for idx in callees}
    return {
        idx: min([idx, *(other for other in reach[idx] if idx in reach[other])])
        for idx in callees
    }


def _reachable(callees: dict[int, list[int]], start: int) -> set[int]:
    seen: set[int] = set()
    pending = list(callees[start])
    while pending:
        idx = pending.pop()
        if idx not in seen:
            seen.add(idx)
            pending.extend(callees[idx])
    return seen


def _callers_of(
    calls: dict[int, list[int]], comps: dict[int, int], idx: int, *, in_cycle: bool
) -> list[int]:
    return [
        caller
        for caller, found in calls.items()
        if idx in found and (comps[caller] == comps[idx]) == in_cycle
    ]


def _waiting(
    nodes: dict[int, Node],
    callers: dict[int, list[int]],
    cycle_callers: dict[int, list[int]],
    comps: dict[int, int],
) -> frozenset[int]:
    """Return the cycle members that only cycle calls reach, except the opener.

    A cycle's opener is its first member when nothing outside calls into it.
    """
    openers = _openers(nodes, callers, comps)
    return frozenset(
        idx
        for idx in nodes
        if not callers[idx] and cycle_callers[idx] and openers[comps[idx]] != idx
    )


def _openers(
    nodes: dict[int, Node], callers: dict[int, list[int]], comps: dict[int, int]
) -> dict[int, int | None]:
    openers: dict[int, int | None] = {}
    for idx, node in nodes.items():
        if node.exempt:
            continue
        if callers[idx]:
            openers[comps[idx]] = None
        else:
            openers.setdefault(comps[idx], idx)
    return openers


def must_precede(model: Model, node: Node, other: Node) -> bool:
    """Report whether node, a public def nothing calls, must sit above other.

    It must when other is a private def nothing calls; exempt defs are free.
    """
    defs = (node.stmt, other.stmt)
    if any(isinstance(stmt, ast.ClassDef) for stmt in defs):
        return False
    if node.exempt or other.exempt or not node.is_public or other.is_public:
        return False
    return node.idx not in model.used and other.idx not in model.used
