import ast
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    Function,
    walk_outside,
)
from pytools.services.lint.linter.funcorder import graph
from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.refs import (
    ImportTimeNames,
    called_names,
)
from pytools.services.lint.linter.funcorder.walls import Walls

type _Users = dict[int, list[int]]


@dataclass(frozen=True)
class Use:
    """Where a class without methods goes: directly above its first user."""

    user: int
    at: int  # the place of that user, or of the class it goes above
    depth: int  # how many such classes it goes above, one the user of the next


@dataclass(frozen=True)
class Classes:
    """Where the classes directly in a scope go."""

    uses: dict[int, Use]  # where each class without methods that can move goes
    inherited: dict[int, frozenset[int]]  # what each user of such classes waits for
    tucked: _Users  # the defs above each class with methods that use it
    _plain: _Users  # the users of each class without methods
    _staying: frozenset[int]  # the classes without methods that can't move

    def first_uses(self, places: dict[int, int]) -> dict[int, Use]:
        """Return where each class in uses goes when its users sit at places."""
        found = _first_uses(self._plain, self._staying, places)
        return {cls: found[cls] for cls in self.uses}


def find_classes(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    refs: dict[int, list[int]],
    effects: list[ImportTimeNames],
    needs: dict[int, frozenset[int]],
    walls: Walls,
) -> Classes:
    """Return where the classes in scope go, from the statements that use them."""
    loads = [found.loads for found in effects]
    users = _users(file, scope, decls, refs, loads)
    used = {cls: found for cls, found in users.items() if found}
    plain = _plain(decls, used)
    uses = _place(decls, plain, walls)
    inherited = _inherited(plain, uses, needs)
    staying = frozenset(plain.keys() - uses.keys())
    return Classes(uses, inherited, _tucked(decls, used), plain, staying)


def _users(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    refs: dict[int, list[int]],
    loads: list[set[str]],
) -> _Users:
    """Return the statements that refer to each class, when run or when called.

    The stubs merged into a decl refer for it.
    """
    names = {decl.stmt.name: idx for idx, decl in decls.items()}
    merged = {stub: idx for idx, decl in decls.items() for stub in decl.span[:-1]}
    referred = [set(refs.get(idx, [])) for idx in range(len(scope.body))]
    for idx, stmt in enumerate(scope.body):
        named = set(loads[idx])
        if idx not in decls and idx not in merged:
            named.update(called_names(file, scope, stmt))
        owner = merged.get(idx, idx)
        referred[owner].update(names[name] for name in named if name in names)
    return {
        cls: [idx for idx, found in enumerate(referred) if cls in found and idx != cls]
        for cls, decl in decls.items()
        if decl.kind is DeclKind.CLASS
    }


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


def _place(
    decls: dict[int, Decl],
    plain: _Users,
    walls: Walls,
) -> dict[int, Use]:
    """Return where each class without methods that can move goes.

    One that can't move stays put, so the classes it uses go above it where it
    is. Each round fixes the classes the round before couldn't move.
    """
    staying = walls.fixed & plain.keys()
    starts = {idx: decl.span.start for idx, decl in decls.items()}
    while True:
        uses = _first_uses(plain, staying, starts)
        movable = _movable(walls, uses, staying)
        stuck = frozenset(uses) - movable
        if stuck <= staying:
            return {cls: use for cls, use in uses.items() if cls in movable}
        staying |= stuck


def _movable(
    walls: Walls, uses: dict[int, Use], staying: frozenset[int]
) -> frozenset[int]:
    """Return the classes that can move to their first user.

    One must not pass a statement its walls forbid, unless that is a deeper
    class moving to the same place, so deeper classes are decided first.
    """
    movable: set[int] = set()
    for cls in sorted(uses, key=lambda idx: -uses[idx].depth):
        use = uses[cls]
        passed = range(cls + 1, use.at) if cls < use.at else range(use.at, cls)
        crossed = walls.crossed(cls, passed)
        is_movable = all(_moves_with(uses, movable, use, idx) for idx in crossed)
        if cls not in staying and is_movable:
            movable.add(cls)
    return frozenset(movable)


def _moves_with(uses: dict[int, Use], movable: set[int], use: Use, idx: int) -> bool:
    other = uses.get(idx)
    is_deeper = other is not None and other.at == use.at and other.depth > use.depth
    return is_deeper and idx in movable


def _inherited(
    plain: _Users, uses: dict[int, Use], needs: dict[int, frozenset[int]]
) -> dict[int, frozenset[int]]:
    """Return what each user of classes without methods that can move waits for.

    Such a class goes above its first user, so a user waits for what it needs
    when defined, and for what the classes it uses need, since they go above it.
    """
    inner = {cls: [other for other in uses if cls in plain[other]] for cls in uses}
    chained = {
        cls: needs[cls].union(*(needs[other] for other in graph.reachable(inner, cls)))
        for cls in uses
    }
    users = {user for cls in uses for user in plain[cls]}
    return {
        user: frozenset(
            need for cls in uses if user in plain[cls] for need in chained[cls]
        )
        for user in users
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
    """Report whether decl has a def with more than a docstring or `...`.

    A def under a compound statement in the class body counts too.
    """
    nodes = walk_outside(decl.stmt.body, (*DEFS, ast.ClassDef))
    return any(isinstance(node, DEFS) and _has_body(node) for node in nodes)


def _has_body(func: Function) -> bool:
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    return not all(
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
        for stmt in body
    )


def _first_uses(
    plain: _Users, staying: frozenset[int], places: dict[int, int]
) -> dict[int, Use]:
    """Return where each class without methods goes, above its first user.

    A user that is such a class and can move counts where that class goes, one
    deeper, so the deeper class sits above it. Any other user sits at its place,
    or at its own index if places leaves it out.
    """
    uses: dict[int, Use] = {}
    for cls in plain:
        _resolve(plain, staying, uses, cls, places)
    return uses


def _resolve(
    plain: _Users,
    staying: frozenset[int],
    uses: dict[int, Use],
    root: int,
    places: dict[int, int],
) -> None:
    """Add root's use to uses, after those of the classes that use it.

    A stack, not recursion, so a long chain of such classes doesn't overflow.
    """
    pending = [root]
    while pending:
        cls = pending[-1]
        moving = [user for user in plain[cls] if user in plain and user not in staying]
        todo = [user for user in moving if user not in uses]
        if todo:
            pending.extend(todo)
        else:
            uses[pending.pop()] = _use(plain[cls], uses, staying, places)


def _use(
    users: list[int],
    uses: dict[int, Use],
    staying: frozenset[int],
    places: dict[int, int],
) -> Use:
    """Return the first of users.

    A use through such a class comes before a direct use at the same place.
    """
    keys = [
        (uses[user].at, 0, -uses[user].depth - 1, user)
        if user in uses and user not in staying
        else (places.get(user, user), 1, 0, user)
        for user in users
    ]
    place, _, depth, user = min(keys)
    return Use(user, place, -depth)
