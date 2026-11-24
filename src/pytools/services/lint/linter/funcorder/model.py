import ast
from dataclasses import dataclass
from itertools import chain, pairwise
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    Function,
    Rule,
)
from pytools.services.lint.linter.analysis.nolint import has_def_nolint
from pytools.services.lint.linter.funcorder import graph
from pytools.services.lint.linter.funcorder.classes import Classes, find_classes
from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.refs import (
    bound_names,
    called_names,
    import_time_names,
)

_DECLS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


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
    classes: Classes  # where the classes go


def build(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Model:
    """Return the calls between the defs and classes directly in scope."""
    stubs = _stubs(scope.body)
    decls = _decls(file, scope, stubs)
    names = {decl.stmt.name: idx for idx, decl in decls.items()}
    refs = {idx: _refs(file, scope, decl, names) for idx, decl in decls.items()}
    callees = {
        idx: [ref for ref in found if decls[ref].kind is not DeclKind.CLASS]
        for idx, found in refs.items()
    }
    reach = {idx: graph.reachable(callees, idx) for idx in callees}
    effects = [import_time_names(file, scope, stmt) for stmt in scope.body]
    loads = [found.loads for found in effects]
    import_time = [graph.import_time_reach(found, names, refs) for found in loads]
    pinned = graph.pinned(import_time, reach)
    calls = {
        idx: [callee for callee in found if _is_enforced(decls, idx, callee, pinned)]
        for idx, found in callees.items()
    }
    comps = graph.components(reach)
    callers = {
        idx: graph.callers_of(calls, comps, idx, in_cycle=False) for idx in decls
    }
    cycles = {idx: graph.callers_of(calls, comps, idx, in_cycle=True) for idx in decls}
    used = frozenset(chain(*import_time, *callees.values()))
    waiting = _waiting(decls, callers, cycles, comps)
    binders = _binders(file, scope.body, decls, loads)
    needs = graph.above(binders)
    classes = find_classes(file, scope, decls, refs, effects, binders)
    return Model(
        scope.body, decls, stubs, calls, callers, cycles, used, waiting, needs, classes
    )


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
    first = idx
    while first - 1 in stubs:
        first -= 1
    exempt = _is_exempt(file, stmt, scope.body[first:idx])
    span = range(first, idx + 1)
    return Decl(idx, stmt, prefix + stmt.name, _kind(stmt), span, exempt)


def _is_exempt(
    file: CheckInput, stmt: Function | ast.ClassDef, merged: list[ast.stmt]
) -> bool:
    """Report whether a funcorder nolint sits on stmt or a def merged into it."""
    defs = [stmt, *(stub for stub in merged if isinstance(stub, DEFS))]
    return any(has_def_nolint(file, func, Rule.FUNCORDER) for func in defs)


def _kind(stmt: Function | ast.ClassDef) -> DeclKind:
    """Return stmt's kind; a dunder is Python's entry point, so it is public."""
    if isinstance(stmt, ast.ClassDef):
        return DeclKind.CLASS
    is_dunder = stmt.name.startswith("__") and stmt.name.endswith("__")
    if is_dunder or not stmt.name.startswith("_"):
        return DeclKind.PUBLIC
    return DeclKind.PRIVATE


def _refs(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decl: Decl,
    names: dict[str, int],
) -> list[int]:
    """Return the decls decl calls or refers to, in the order it first does.

    The stubs decl replaces, such as a property getter, call for it too.
    """
    found = [
        names[name]
        for part in decl.span
        for name in called_names(file, scope, scope.body[part])
        if name in names
    ]
    return [idx for idx in dict.fromkeys(found) if idx != decl.idx]


def _is_enforced(
    decls: dict[int, Decl], caller: int, callee: int, pinned: set[int]
) -> bool:
    is_exempt = decls[caller].exempt or decls[callee].exempt
    return not is_exempt and callee not in pinned


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


def _binders(
    file: CheckInput,
    stmts: list[ast.stmt],
    decls: dict[int, Decl],
    loads: list[set[str]],
) -> dict[int, frozenset[int]]:
    """Return the statements that bind or delete a name each decl uses when defined.

    The stubs merged into a decl are defined with it.
    """
    binds = [bound_names(file, stmt) for stmt in stmts]
    defined = {
        idx: {name for part in decl.span for name in loads[part]}
        for idx, decl in decls.items()
    }
    return {
        idx: frozenset(other for other, names in enumerate(binds) if names & used)
        for idx, used in defined.items()
    }


def must_precede(model: Model, decl: Decl, other: Decl) -> bool:
    """Report whether decl, a public def nothing calls, must sit above other.

    It must when other is a private def nothing calls.
    """
    is_unused = decl.idx not in model.used and other.idx not in model.used
    is_ranked = not (decl.exempt or other.exempt) and is_unused
    return (decl.kind, other.kind) == (DeclKind.PUBLIC, DeclKind.PRIVATE) and is_ranked
