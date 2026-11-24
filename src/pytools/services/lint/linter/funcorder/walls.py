import ast
from bisect import bisect_left
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import DEFS
from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.inert import is_inert
from pytools.services.lint.linter.funcorder.refs import ImportTimeNames


@dataclass(frozen=True)
class Walls:
    """The statements each decl in a scope must not move past."""

    binders: dict[int, frozenset[int]]  # bind a name each decl reads when defined
    barriers: frozenset[int]  # may run code or bind a name
    walled: frozenset[int]  # the decls that must not move past a barrier
    runs: frozenset[int]  # may run code, which may use any name the scope binds

    def crossed(self, idx: int, passed: Collection[int]) -> frozenset[int]:
        """Return the statements of passed that the decl at idx must not pass."""
        found = self.binders.get(idx, frozenset()).intersection(passed)
        if idx in self.walled:
            found |= self.barriers.intersection(passed)
        return found

    def keeps(self, order: list[int]) -> bool:
        """Report whether order keeps what runs when the scope is defined.

        No statement passes one that may run code, and no decl passes a binder.
        """
        rank = {idx: pos for pos, idx in enumerate(order)}
        runs = sorted(self.runs)
        ranks = [rank[idx] for idx in runs]
        is_ordered = ranks == sorted(ranks) and all(
            bisect_left(runs, idx) == bisect_left(ranks, rank[idx]) for idx in order
        )
        return is_ordered and not any(
            (idx < other) != (rank[idx] < rank[other])
            for idx, found in self.binders.items()
            for other in found
        )


def find_walls(
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    effects: list[ImportTimeNames],
    binders: dict[int, frozenset[int]],
    kept: frozenset[int],
    bindings: Counter[str],
) -> Walls:
    """Return the statements each decl in a scope must not move past.

    Its binders bind a name it reads when defined. Any statement but an inert
    decl that runs no scope code may run code or bind a name, so a decl whose
    definition may run code must not pass one, nor may one that reads a name the
    scope may bind, nor, in a class scope, a class that reads a name its body
    doesn't bind. A decl's stubs, such as overloads, count as part of it.
    """
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    active = {idx for idx, decl in decls.items() if not _is_inert_decl(scope, decl)}
    calm = {part for idx in decls.keys() - kept - active for part in decls[idx].span}
    barriers = frozenset(range(len(effects))) - calm
    reads = {idx: _reads(effects, decl) for idx, decl in decls.items()}
    walled = active | {idx for idx in decls if reads[idx] & bindings.keys()}
    if isinstance(scope, ast.ClassDef):
        walled |= {cls for cls in classes if effects[cls].reads - effects[cls].binds}
    return Walls(binders, barriers, frozenset(walled), _runs(scope, decls, active))


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
    return isinstance(stmt, (*DEFS, ast.ClassDef)) and bool(stmt.decorator_list)
