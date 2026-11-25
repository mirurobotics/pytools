import ast
from bisect import bisect_left
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    Function,
    walk_outside,
)
from pytools.services.lint.linter.analysis.names import outer_parts
from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.inert import is_inert
from pytools.services.lint.linter.funcorder.refs import ImportTimeNames, scope_bindings


@dataclass(frozen=True)
class Walls:
    """The statements each decl in a scope must not move past."""

    binders: dict[int, frozenset[int]]  # bind a name each statement reads when run
    barriers: frozenset[int]  # may run code or bind a name
    walled: frozenset[int]  # the decls that must not move past a barrier
    runs: frozenset[int]  # may run code, which may use any name the scope binds
    rivals: list[list[int]]  # bind the same name, so the last one wins
    fixed: frozenset[int]  # the decls that never move, exempt classes included

    def may_pass(self, moved: Collection[int], passed: Collection[int]) -> bool:
        """Report whether the decls moved may move together past those passed."""
        if not self.fixed.isdisjoint(moved):
            return False
        return not any(self.crossed(idx, passed) for idx in moved)

    def crossed(self, idx: int, passed: Collection[int]) -> frozenset[int]:
        """Return the statements of passed that the decl at idx must not pass."""
        found = self.binders.get(idx, frozenset()).intersection(passed)
        if idx in self.walled:
            found |= self.barriers.intersection(passed)
        return found

    def keeps(self, order: list[int]) -> bool:
        """Report whether order keeps what runs when the scope is defined.

        No statement passes one that may run code, binds a name it binds, or
        binds a name it reads.
        """
        rank = {idx: pos for pos, idx in enumerate(order)}
        runs = sorted(self.runs)
        ranks = [rank[idx] for idx in runs]
        is_ordered = ranks == sorted(ranks) and all(
            bisect_left(runs, idx) == bisect_left(ranks, rank[idx]) for idx in order
        )
        groups = [[rank[idx] for idx in group] for group in self.rivals]
        is_bound = all(group == sorted(group) for group in groups)
        is_below = not any(
            (idx < other) != (rank[idx] < rank[other])
            for idx, found in self.binders.items()
            for other in found
        )
        return is_ordered and is_bound and is_below


def find_walls(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    effects: list[ImportTimeNames],
    binders: dict[int, frozenset[int]],
) -> Walls:
    """Return the statements each decl in a scope must not move past.

    Its binders bind a name it reads when defined. Any statement but an inert
    decl that runs no scope code may run code or bind a name, so a decl whose
    definition may run code must not pass one, nor may one that reads a name the
    scope may bind, nor, in a class scope, a class that reads a name its body
    doesn't bind. A decl's stubs, such as overloads, count as part of it.
    """
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    bindings = scope_bindings(file, scope)
    shadowed = _shadowed_classes(decls, bindings)
    kept = _runs_code(decls, effects, bindings) | shadowed | _writes_outer(decls)
    exempt = {idx for idx in classes if decls[idx].exempt}
    active = {idx for idx, decl in decls.items() if not _is_inert_decl(scope, decl)}
    calm = {part for idx in decls.keys() - kept - active for part in decls[idx].span}
    barriers = frozenset(range(len(effects))) - calm
    reads = {idx: _reads(effects, decl) for idx, decl in decls.items()}
    walled = active | {idx for idx in decls if reads[idx] & bindings.keys()}
    if isinstance(scope, ast.ClassDef):
        walled |= {cls for cls in classes if effects[cls].reads - effects[cls].binds}
    runs = _runs(scope, decls, active)
    bound = _bound_by(effects)
    rivals = [group for group in bound.values() if len(group) > 1]
    readers = _readers(effects, bound) | binders
    return Walls(readers, barriers, frozenset(walled), runs, rivals, kept | exempt)


def _shadowed_classes(decls: dict[int, Decl], bindings: Counter[str]) -> frozenset[int]:
    """Return the classes whose name another statement may bind or delete.

    A use of that name may mean another binding, so such a class never moves. A
    global declaration may bind it too, and a star import may bind any name.
    """
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    if bindings["*"]:
        return frozenset(classes)
    return frozenset(cls for cls in classes if bindings[decls[cls].stmt.name] > 1)


def _runs_code(
    decls: dict[int, Decl], effects: list[ImportTimeNames], bindings: Counter[str]
) -> frozenset[int]:
    """Return the decls whose definition may run code from the scope.

    That code may read a statement a move would pass, so such a decl never
    moves. It may run when a name bound in the scope is used other than by only
    loading it, but a class body's value may name a bare def.
    """
    local = {name for found in effects for name in found.binds}
    risky = local - _bare_def_names(decls, bindings)
    return frozenset(
        idx
        for idx, decl in decls.items()
        for part in decl.span
        if effects[part].called & local or effects[part].stored & risky
    )


def _bare_def_names(decls: dict[int, Decl], bindings: Counter[str]) -> set[str]:
    """Return the names that only an undecorated def binds."""
    return {
        decl.stmt.name
        for decl in decls.values()
        if isinstance(decl.stmt, DEFS)
        and not decl.stmt.decorator_list
        and bindings[decl.stmt.name] == 1
    }


def _writes_outer(decls: dict[int, Decl]) -> frozenset[int]:
    """Return the classes whose header has a walrus, or body a global or nonlocal.

    A walrus in the body binds only in the class namespace.
    """
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    return frozenset(idx for idx in classes if _has_outer_write(decls[idx].stmt))


def _has_outer_write(stmt: Function | ast.ClassDef) -> bool:
    if not isinstance(stmt, ast.ClassDef):
        return False
    in_header = [node for part in outer_parts(stmt) for node in ast.walk(part)]
    is_walrus = any(isinstance(node, ast.NamedExpr) for node in in_header)
    nodes = walk_outside(stmt.body, DEFS)
    is_declared = any(isinstance(node, (ast.Global, ast.Nonlocal)) for node in nodes)
    return is_walrus or is_declared


def _is_inert_decl(scope: ast.Module | ast.ClassDef, decl: Decl) -> bool:
    """Report whether defining decl and its stubs surely runs no code."""
    stubs = [scope.body[part] for part in decl.span[:-1]]
    is_calm = all(isinstance(stub, DEFS) and is_inert(stub) for stub in stubs)
    return is_calm and is_inert(decl.stmt)


def _reads(effects: list[ImportTimeNames], decl: Decl) -> set[str]:
    """Return the names decl and its stubs read when defined."""
    return {name for part in decl.span for name in effects[part].reads}


def _runs(
    scope: ast.Module | ast.ClassDef, decls: dict[int, Decl], active: set[int]
) -> frozenset[int]:
    """Return the statements that may run code when a fix moves them.

    A fix trusts no decorator by name, since an import can rename any.
    """
    parts = {part: idx for idx, decl in decls.items() for part in decl.span}
    loud = active | {parts[part] for part in parts if _is_decorated(scope.body[part])}
    return frozenset(
        idx
        for idx, stmt in enumerate(scope.body)
        if (parts[idx] in loud if idx in parts else not is_inert(stmt))
    )


def _is_decorated(stmt: ast.stmt) -> bool:
    """Report whether stmt is, or a class body holds, a decorated def or class."""
    is_class = isinstance(stmt, ast.ClassDef)
    nodes: Iterable[ast.AST] = ast.walk(stmt) if is_class else [stmt]
    return any(
        isinstance(node, (*DEFS, ast.ClassDef)) and bool(node.decorator_list)
        for node in nodes
    )


def _bound_by(effects: list[ImportTimeNames]) -> dict[str, list[int]]:
    """Return the statements that bind each name, in order."""
    found: dict[str, list[int]] = {}
    for idx, effect in enumerate(effects):
        for name in effect.binds:
            found.setdefault(name, []).append(idx)
    return found


def _readers(
    effects: list[ImportTimeNames], bound: dict[str, list[int]]
) -> dict[int, frozenset[int]]:
    """Return the statements that bind a name each statement reads when run."""
    return {
        idx: frozenset(other for name in effect.reads for other in bound.get(name, []))
        for idx, effect in enumerate(effects)
    }
