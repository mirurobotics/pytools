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
from pytools.services.lint.linter.funcorder import graph
from pytools.services.lint.linter.funcorder.refs import (
    bound_names,
    called_names,
    import_time_names,
)

_DECLS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

type _Users = dict[int, list[int]]


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
    first: int  # its first stub, such as a property getter, or idx without one


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
    plain: _Users  # the users of each used class without methods
    plain_needs: dict[int, frozenset[int]]  # needs, with those of classes it uses
    tucked: _Users  # the defs above each class with methods that use it


def build(file: CheckInput, scope: ast.Module | ast.ClassDef) -> Model:
    """Return the calls between the defs and classes directly in scope."""
    stmts = scope.body
    stubs = _stubs(stmts)
    decls = _decls(file, scope, stubs)
    names = {decl.stmt.name: idx for idx, decl in decls.items()}
    refs = {idx: _refs(file, scope, decl, names) for idx, decl in decls.items()}
    callees = {
        idx: [ref for ref in found if decls[ref].kind is not DeclKind.CLASS]
        for idx, found in refs.items()
    }
    reach = {idx: graph.reachable(callees, idx) for idx in callees}
    loads = [import_time_names(stmt) for stmt in stmts]
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
    needs = _needs(file, stmts, decls, loads)
    plain, tucked = _class_users(file, scope, decls, names, refs, loads)
    classes = plain, _plain_needs(plain, needs), tucked
    return Model(
        stmts, decls, stubs, calls, callers, cycles, used, waiting, needs, *classes
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
    kind = _kind(file, stmt, scope.body[first:idx])
    return Decl(idx, stmt, prefix + stmt.name, kind, first)


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
    names: dict[str, int],
) -> list[int]:
    """Return the decls decl calls or refers to, in the order it first does.

    The stubs decl replaces, such as a property getter, call for it too.
    """
    stmts = scope.body[decl.first : decl.idx + 1]
    found = [
        names[name]
        for stmt in stmts
        for name in called_names(file, scope, stmt)
        if name in names
    ]
    return [idx for idx in dict.fromkeys(found) if idx != decl.idx]


def _is_enforced(
    decls: dict[int, Decl], caller: int, callee: int, pinned: set[int]
) -> bool:
    kinds = (decls[caller].kind, decls[callee].kind)
    return DeclKind.EXEMPT not in kinds and callee not in pinned


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
    file: CheckInput,
    stmts: list[ast.stmt],
    decls: dict[int, Decl],
    loads: list[set[str]],
) -> dict[int, frozenset[int]]:
    """Return the statements above each decl that it uses when defined.

    The stubs merged into a decl are defined with it.
    """
    binds = [bound_names(file, stmt) for stmt in stmts]
    defined = {
        idx: {name for found in loads[decl.first : idx + 1] for name in found}
        for idx, decl in decls.items()
    }
    return {
        idx: frozenset(other for other in range(idx) if binds[other] & defined[idx])
        for idx in decls
    }


def _class_users(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    names: dict[str, int],
    refs: dict[int, list[int]],
    loads: list[set[str]],
) -> tuple[_Users, _Users]:
    """Return the users of each class without methods, then of each with them.

    A class's users are the statements that refer to it, when run or when
    called. The stubs merged into a decl refer for it. A class with methods
    keeps only the defs above it.
    """
    merged = {
        stub: idx for idx, decl in decls.items() for stub in range(decl.first, idx)
    }
    referred = [set(refs.get(idx, [])) for idx in range(len(scope.body))]
    for idx, stmt in enumerate(scope.body):
        named = set(loads[idx])
        if idx not in decls and idx not in merged:
            named.update(called_names(file, scope, stmt))
        owner = merged.get(idx, idx)
        referred[owner].update(names[name] for name in named if name in names)
    users = {
        cls: [idx for idx, found in enumerate(referred) if cls in found and idx != cls]
        for cls, decl in decls.items()
        if decl.kind is DeclKind.CLASS
    }
    used = {cls: found for cls, found in users.items() if found}
    return _plain(decls, used), _tucked(decls, used)


def _plain(decls: dict[int, Decl], users: _Users) -> _Users:
    """Return the users of each class without methods.

    Such classes that use each other in a cycle are left out, since none of
    them has a first user to go above.
    """
    plain = {cls: found for cls, found in users.items() if not _has_methods(decls[cls])}
    within = {
        cls: [user for user in found if user in plain] for cls, found in plain.items()
    }
    return {
        cls: found
        for cls, found in plain.items()
        if cls not in graph.reachable(within, cls)
    }


def _tucked(decls: dict[int, Decl], users: _Users) -> _Users:
    """Return the defs above each class with methods that use it."""
    defs = {idx for idx, decl in decls.items() if decl.kind is not DeclKind.CLASS}
    above = {
        cls: [user for user in found if user < cls and user in defs]
        for cls, found in users.items()
        if _has_methods(decls[cls])
    }
    return {cls: found for cls, found in above.items() if found}


def _has_methods(decl: Decl) -> bool:
    """Report whether decl has a def with more than a docstring or `...`."""
    return any(isinstance(stmt, DEFS) and _has_body(stmt) for stmt in decl.stmt.body)


def _has_body(func: Function) -> bool:
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    return not all(
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
        for stmt in body
    )


def _plain_needs(
    plain: _Users, needs: dict[int, frozenset[int]]
) -> dict[int, frozenset[int]]:
    """Return what each class without methods needs when defined.

    The classes it uses go above it, so what they need counts as its own.
    """
    uses = {cls: [other for other in plain if cls in plain[other]] for cls in plain}
    return {
        cls: needs[cls].union(*(needs[other] for other in graph.reachable(uses, cls)))
        for cls in plain
    }


def must_precede(model: Model, decl: Decl, other: Decl) -> bool:
    """Report whether decl, a public def nothing calls, must sit above other.

    It must when other is a private def nothing calls.
    """
    is_unused = decl.idx not in model.used and other.idx not in model.used
    return (decl.kind, other.kind) == (DeclKind.PUBLIC, DeclKind.PRIVATE) and is_unused
