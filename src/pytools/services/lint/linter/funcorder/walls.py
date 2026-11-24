import ast
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.inert import is_inert
from pytools.services.lint.linter.funcorder.refs import ImportTimeNames

_DECLS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class Walls:
    """The statements each decl in a scope must not move past."""

    binders: dict[int, frozenset[int]]  # bind a name each decl reads when defined
    barriers: frozenset[int]  # may run code or bind a name
    walled: frozenset[int]  # the decls that must not move past a barrier

    def crossed(self, idx: int, passed: Collection[int]) -> frozenset[int]:
        """Return the statements of passed that the decl at idx must not pass."""
        found = self.binders.get(idx, frozenset()).intersection(passed)
        if idx in self.walled:
            found |= self.barriers.intersection(passed)
        return found


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
    merged = {idx: scope.body[decl.first : idx + 1] for idx, decl in decls.items()}
    active = {idx for idx, stmts in merged.items() if not _is_inert(stmts)}
    barriers = frozenset(range(len(effects))) - (decls.keys() - kept - active)
    reads = {idx: _reads(effects, decl) for idx, decl in decls.items()}
    walled = active | {idx for idx in decls if reads[idx] & bindings.keys()}
    if isinstance(scope, ast.ClassDef):
        walled |= {cls for cls in classes if effects[cls].reads - effects[cls].binds}
    return Walls(binders, barriers, frozenset(walled))


def _is_inert(stmts: list[ast.stmt]) -> bool:
    return all(isinstance(stmt, _DECLS) and is_inert(stmt) for stmt in stmts)


def _reads(effects: list[ImportTimeNames], decl: Decl) -> set[str]:
    """Return the names decl and its stubs read when defined."""
    merged = effects[decl.first : decl.idx + 1]
    return {name for found in merged for name in found.reads}
