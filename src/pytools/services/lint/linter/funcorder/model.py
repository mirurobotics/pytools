import ast
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput, Function, Rule
from pytools.services.lint.linter.analysis.nolint import has_def_nolint
from pytools.services.lint.linter.funcorder.refs import called_names, import_time_names

_DEFS: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
_DECLS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class Decl:
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
    decls: dict[int, Decl]
    stubs: frozenset[int]  # defs the next def of the same name replaces
    calls: dict[int, list[int]]  # enforced callees, in the order first called
    callers: dict[int, list[int]]  # enforced callers outside the callee's cycle
    cycle_callers: dict[int, list[int]]
    used: frozenset[int]  # defs referenced anywhere in the scope
    waiting: frozenset[int]  # cycle members placed only after a cycle caller


def build(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Model:
    """Return the calls between the defs and classes directly in scope."""
    stubs = _stubs(scope.body)
    decls = _decls(file, scope, stubs)
    by_name = {
        decl.stmt.name: idx
        for idx, decl in decls.items()
        if not isinstance(decl.stmt, ast.ClassDef)
    }
    callees = {idx: _callees(file, scope, decl, by_name) for idx, decl in decls.items()}
    pinned = _pinned(scope.body, by_name)
    calls = {
        idx: [callee for callee in found if _is_enforced(decls, idx, callee, pinned)]
        for idx, found in callees.items()
    }
    comps = _components(callees)
    callers = {idx: _callers_of(calls, comps, idx, in_cycle=False) for idx in decls}
    cycles = {idx: _callers_of(calls, comps, idx, in_cycle=True) for idx in decls}
    used = frozenset(pinned.union(*callees.values()))
    waiting = _waiting(decls, callers, cycles, comps)
    return Model(scope.body, decls, stubs, calls, callers, cycles, used, waiting)


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


def _decls(
    file: CheckInput, scope: ast.Module | ast.ClassDef, stubs: frozenset[int]
) -> dict[int, Decl]:
    prefix = f"{scope.name}." if isinstance(scope, ast.ClassDef) else ""
    return {
        idx: _decl(file, idx, stmt, prefix)
        for idx, stmt in enumerate(scope.body)
        if isinstance(stmt, _DECLS) and idx not in stubs
    }


def _decl(
    file: CheckInput, idx: int, stmt: Function | ast.ClassDef, prefix: str
) -> Decl:
    is_def = not isinstance(stmt, ast.ClassDef)
    exempt = is_def and has_def_nolint(file, stmt, Rule.FUNCORDER)
    return Decl(idx, stmt, prefix + stmt.name, _is_public(stmt.name), exempt)


def _is_public(name: str) -> bool:
    """Report whether name is public; a dunder is Python's entry point."""
    is_dunder = name.startswith("__") and name.endswith("__")
    return is_dunder or not name.startswith("_")


def _callees(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decl: Decl,
    by_name: dict[str, int],
) -> list[int]:
    """Return the defs decl calls, in the order it first calls them."""
    names = called_names(file, scope, decl.stmt)
    found = [by_name[name] for name in names if name in by_name]
    return [idx for idx in dict.fromkeys(found) if idx != decl.idx]


def _pinned(stmts: list[ast.stmt], by_name: dict[str, int]) -> set[int]:
    """Return the defs stmts use at import time, which must stay above that use."""
    return {by_name[name] for name in import_time_names(stmts) if name in by_name}


def _is_enforced(
    decls: dict[int, Decl], caller: int, callee: int, pinned: set[int]
) -> bool:
    is_exempt = decls[caller].exempt or decls[callee].exempt
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
        if decl.exempt:
            continue
        if callers[idx]:
            openers[comps[idx]] = None
        else:
            openers.setdefault(comps[idx], idx)
    return openers


def must_precede(model: Model, decl: Decl, other: Decl) -> bool:
    """Report whether decl, a public def nothing calls, must sit above other.

    It must when other is a private def nothing calls; exempt defs are free.
    """
    defs = (decl.stmt, other.stmt)
    if any(isinstance(stmt, ast.ClassDef) for stmt in defs):
        return False
    if decl.exempt or other.exempt or not decl.is_public or other.is_public:
        return False
    return decl.idx not in model.used and other.idx not in model.used
