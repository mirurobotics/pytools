import ast
from dataclasses import dataclass
from enum import Enum, auto
from itertools import chain, pairwise
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    Function,
    Rule,
)
from pytools.services.lint.linter.analysis.nolint import has_def_nolint
from pytools.services.lint.linter.funcorder.refs import (
    bound_names,
    called_names,
    import_time_names,
)

_DECLS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class DeclKind(Enum):
    """How a decl takes part in its scope's order."""

    PUBLIC = auto()
    PRIVATE = auto()  # named with a leading underscore, and not a dunder
    EXEMPT = auto()  # a def with a nolint, which keeps its place
    CLASS = auto()  # one caller, through its methods' calls


@dataclass(frozen=True)
class Decl:
    """A def or class in a scope, one of the units the scope is ordered by."""

    idx: int
    stmt: Function | ast.ClassDef
    name: str
    kind: DeclKind


@dataclass(frozen=True)
class Model:
    """The calls between the defs and classes directly in a scope.

    A class counts as one caller, through its methods' calls. Calls out of or
    into an exempt def, and into a def an import-time use reaches and a caller
    below that use reaches too, are not enforced.
    """

    stmts: list[ast.stmt]
    decls: dict[int, Decl]
    stubs: frozenset[int]  # defs the next def of the same name replaces
    calls: dict[int, list[int]]  # enforced callees, in the order first called
    callers: dict[int, list[int]]  # enforced callers outside the callee's cycle
    cycle_callers: dict[int, list[int]]
    used: frozenset[int]  # defs referenced anywhere in the scope
    waiting: frozenset[int]  # cycle members placed only after a cycle caller
    needs: dict[int, frozenset[int]]  # statements a decl uses when defined


def build(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Model:
    """Return the calls between the defs and classes directly in scope."""
    stubs = _stubs(scope.body)
    decls = _decls(file, scope, stubs)
    names = {decl.stmt.name: idx for idx, decl in decls.items()}
    refs = {idx: _refs(file, scope, decl, stubs, names) for idx, decl in decls.items()}
    callees = {
        idx: [ref for ref in found if decls[ref].kind is not DeclKind.CLASS]
        for idx, found in refs.items()
    }
    reach = {idx: _reachable(callees, idx) for idx in callees}
    import_time = [_import_time_reach(stmt, names, refs) for stmt in scope.body]
    pinned = _pinned(import_time, reach)
    calls = {
        idx: [callee for callee in found if _is_enforced(decls, idx, callee, pinned)]
        for idx, found in callees.items()
    }
    comps = _components(reach)
    callers = {idx: _callers_of(calls, comps, idx, in_cycle=False) for idx in decls}
    cycles = {idx: _callers_of(calls, comps, idx, in_cycle=True) for idx in decls}
    used = frozenset(chain(*import_time, *callees.values()))
    waiting = _waiting(decls, callers, cycles, comps)
    needs = _needs(file, scope.body, decls)
    return Model(scope.body, decls, stubs, calls, callers, cycles, used, waiting, needs)


def _stubs(stmts: list[ast.stmt]) -> frozenset[int]:
    """Return the defs directly followed by a def of the same name.

    Overloads and property getters are one function with the def they precede.
    """
    pairs = enumerate(pairwise(stmts))
    return frozenset(idx for idx, pair in pairs if _is_redefined(*pair))


def _is_redefined(stmt: ast.stmt, after: ast.stmt) -> bool:
    if not isinstance(stmt, DEFS) or not isinstance(after, DEFS):
        return False
    return stmt.name == after.name


def _decls(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stubs: frozenset[int]
) -> dict[int, Decl]:
    return {
        idx: _decl(file, scope, stubs, idx, stmt)
        for idx, stmt in enumerate(scope.body)
        if isinstance(stmt, _DECLS) and idx not in stubs
    }


def _decl(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    stubs: frozenset[int],
    idx: int,
    stmt: Function | ast.ClassDef,
) -> Decl:
    prefix = f"{scope.name}." if isinstance(scope, ast.ClassDef) else ""
    merged = scope.body[_first_merged(stubs, idx) : idx]
    return Decl(idx, stmt, prefix + stmt.name, _kind(file, stmt, merged))


def _kind(
    file: CheckInput, stmt: Function | ast.ClassDef, merged: list[ast.stmt]
) -> DeclKind:
    """Return stmt's kind; a dunder is Python's entry point, so it is public.

    A nolint on any def merged into stmt exempts it too.
    """
    if isinstance(stmt, ast.ClassDef):
        return DeclKind.CLASS
    defs = [stmt, *(stub for stub in merged if isinstance(stub, DEFS))]
    if any(has_def_nolint(file, func, Rule.FUNCORDER) for func in defs):
        return DeclKind.EXEMPT
    is_dunder = stmt.name.startswith("__") and stmt.name.endswith("__")
    if is_dunder or not stmt.name.startswith("_"):
        return DeclKind.PUBLIC
    return DeclKind.PRIVATE


def _refs(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decl: Decl,
    stubs: frozenset[int],
    names: dict[str, int],
) -> list[int]:
    """Return the decls decl calls or refers to, in the order it first does.

    The stubs decl replaces, such as a property getter, call for it too.
    """
    stmts = scope.body[_first_merged(stubs, decl.idx) : decl.idx + 1]
    found = [
        names[name]
        for stmt in stmts
        for name in called_names(file, scope, stmt)
        if name in names
    ]
    return [idx for idx in dict.fromkeys(found) if idx != decl.idx]


def _first_merged(stubs: frozenset[int], idx: int) -> int:
    """Return the first of the defs merged into the decl at idx."""
    while idx - 1 in stubs:
        idx -= 1
    return idx


def _import_time_reach(
    stmt: ast.stmt, names: dict[str, int], refs: dict[int, list[int]]
) -> set[int]:
    """Return the decls stmt uses at import time, and every decl they refer to.

    Following every reference, not only the calls that run, may pin more than
    needed, but never too little.
    """
    used = {names[name] for name in import_time_names(stmt) if name in names}
    return used.union(*(_reachable(refs, idx) for idx in used))


def _reachable(callees: dict[int, list[int]], start: int) -> set[int]:
    seen: set[int] = set()
    pending = list(callees[start])
    while pending:
        idx = pending.pop()
        if idx not in seen:
            seen.add(idx)
            pending.extend(callees[idx])
    return seen


def _pinned(import_time: list[set[int]], reach: dict[int, set[int]]) -> set[int]:
    """Return the decls an import-time use needs that a caller below it reaches.

    The rule would move such a decl below that caller, past the use. A def
    counts as below its own decorators and defaults.
    """
    last = {idx: caller for caller in sorted(reach) for idx in reach[caller]}
    return {
        idx
        for use, needed in enumerate(import_time)
        for idx in needed
        if last.get(idx, -1) >= use
    }


def _is_enforced(
    decls: dict[int, Decl], caller: int, callee: int, pinned: set[int]
) -> bool:
    kinds = (decls[caller].kind, decls[callee].kind)
    return DeclKind.EXEMPT not in kinds and callee not in pinned


def _components(reach: dict[int, set[int]]) -> dict[int, int]:
    """Label each def with its cycle's first member, or itself outside a cycle."""
    return {
        idx: min([idx, *(other for other in reach[idx] if idx in reach[other])])
        for idx in reach
    }


def _callers_of(
    calls: dict[int, list[int]], comps: dict[int, int], idx: int, *, in_cycle: bool
) -> list[int]:
    return [
        caller
        for caller, found in calls.items()
        if idx in found and (comps[caller] == comps[idx]) == in_cycle
    ]


def _waiting(
    decls: dict[int, Decl],
    callers: dict[int, list[int]],
    cycle_callers: dict[int, list[int]],
    comps: dict[int, int],
) -> frozenset[int]:
    """Return the cycle members that only cycle calls reach, except the opener.

    A cycle's opener is its first member when nothing outside calls into it.
    """
    openers = _openers(decls, callers, comps)
    return frozenset(
        idx
        for idx in decls
        if not callers[idx] and cycle_callers[idx] and openers[comps[idx]] != idx
    )


def _openers(
    decls: dict[int, Decl], callers: dict[int, list[int]], comps: dict[int, int]
) -> dict[int, int | None]:
    openers: dict[int, int | None] = {}
    for idx, decl in decls.items():
        if decl.kind is DeclKind.EXEMPT:
            continue
        if callers[idx]:
            openers[comps[idx]] = None
        else:
            openers.setdefault(comps[idx], idx)
    return openers


def _needs(
    file: CheckInput, stmts: list[ast.stmt], decls: dict[int, Decl]
) -> dict[int, frozenset[int]]:
    """Return the statements above each decl that it uses when defined."""
    binds = {
        idx: bound_names(file, stmt)
        for idx, stmt in enumerate(stmts)
        if idx not in decls
    }
    loads = {idx: import_time_names(decl.stmt) for idx, decl in decls.items()}
    return {
        idx: frozenset(
            stmt for stmt, bound in binds.items() if stmt < idx and bound & loads[idx]
        )
        for idx in decls
    }


def must_precede(model: Model, decl: Decl, other: Decl) -> bool:
    """Report whether decl, a public def nothing calls, must sit above other.

    It must when other is a private def nothing calls.
    """
    is_unused = decl.idx not in model.used and other.idx not in model.used
    return (decl.kind, other.kind) == (DeclKind.PUBLIC, DeclKind.PRIVATE) and is_unused
