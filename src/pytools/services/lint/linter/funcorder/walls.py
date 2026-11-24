from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.inert import is_inert
from pytools.services.lint.linter.funcorder.refs import ImportTimeNames


@dataclass(frozen=True)
class Walls:
    """The statements each decl in a scope must not move past."""

    binders: dict[int, frozenset[int]]  # bind a name each decl reads when defined
    walls: frozenset[int]  # may run code or bind a name
    walled: frozenset[int]  # the decls that must not move past a wall

    def crossed(self, idx: int, passed: Collection[int]) -> frozenset[int]:
        """Return the statements of passed that the decl at idx must not pass."""
        found = self.binders.get(idx, frozenset()).intersection(passed)
        if idx in self.walled:
            found |= self.walls.intersection(passed)
        return found


def find_walls(
    decls: dict[int, Decl],
    effects: list[ImportTimeNames],
    binders: dict[int, frozenset[int]],
    kept: frozenset[int],
    bindings: Counter[str],
    *,
    is_class: bool,
) -> Walls:
    """Return the statements each decl in a scope must not move past.

    Its binders bind a name it reads when defined. Any statement but an inert
    decl that runs no scope code may run code or bind a name, so a decl whose
    definition may run code must not pass one, nor may one that reads a name the
    scope may bind, nor, in a class scope, a class that reads a name its body
    doesn't bind.
    """
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    active = {idx for idx, decl in decls.items() if not is_inert(decl.stmt)}
    walls = frozenset(range(len(effects))) - (decls.keys() - kept - active)
    walled = active | {idx for idx in decls if effects[idx].reads & bindings.keys()}
    if is_class:
        walled |= {cls for cls in classes if effects[cls].reads - effects[cls].binds}
    return Walls(binders, walls, frozenset(walled))
