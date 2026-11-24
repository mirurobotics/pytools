import ast
from collections import Counter
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
    bound_names,
    called_names,
)

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
    kept: frozenset[int]  # decls whose definition may run scope code, shadowed classes
    blocked: dict[int, frozenset[int]]  # the statements each class must not move past


def find_classes(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    refs: dict[int, list[int]],
    effects: list[ImportTimeNames],
    binders: dict[int, frozenset[int]],
) -> Classes:
    """Return where the classes in scope go, from the statements that use them.

    Binders are the statements that bind a name each decl uses when defined.
    """
    loads = [found.loads for found in effects]
    users = _users(file, scope, decls, refs, loads)
    used = {cls: found for cls, found in users.items() if found}
    changes = [bound_names(file, stmt) for stmt in scope.body]
    rebound = _global_names(scope)
    kept = _runs_code(decls, effects) | _shadowed_classes(decls, changes, rebound)
    plain = _plain(decls, used)
    bound = frozenset().union(*changes, rebound)
    blocked = _blocked(decls, effects, binders, kept, bound)
    uses = _place(decls, plain, blocked, kept)
    inherited = _inherited(plain, uses, graph.above(binders))
    return Classes(uses, inherited, _tucked(decls, used), kept, blocked)


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
    return {
        cls: [idx for idx, found in enumerate(referred) if cls in found and idx != cls]
        for cls, decl in decls.items()
        if decl.kind is DeclKind.CLASS
    }


def _global_names(scope: ast.Module | ast.ClassDef) -> frozenset[str]:
    """Return the names declared global anywhere in scope, which it may rebind."""
    nodes = [node for stmt in scope.body for node in ast.walk(stmt)]
    found = [node for node in nodes if isinstance(node, ast.Global)]
    return frozenset(name for node in found for name in node.names)


def _runs_code(
    decls: dict[int, Decl], effects: list[ImportTimeNames]
) -> frozenset[int]:
    """Return the decls whose definition may run code from the scope.

    That code may read a statement a move would pass, so such a decl never
    moves. Its definition may run it when it uses a name bound in the scope, or
    in that definition, other than by only loading it. A class body's value may
    be a def's name, since a function has no `__set_name__` to run.
    """
    local = {name for found in effects for name in found.binds}
    risky = local - _bare_def_names(decls, effects)
    return frozenset(
        idx
        for idx in decls
        if effects[idx].called & local or effects[idx].stored & risky
    )


def _bare_def_names(decls: dict[int, Decl], effects: list[ImportTimeNames]) -> set[str]:
    """Return the names that only undecorated defs bind."""
    defs = {
        idx
        for idx, decl in decls.items()
        if isinstance(decl.stmt, DEFS) and not decl.stmt.decorator_list
    }
    others = [found.binds for idx, found in enumerate(effects) if idx not in defs]
    return {decls[idx].stmt.name for idx in defs}.difference(*others)


def _shadowed_classes(
    decls: dict[int, Decl], changes: list[frozenset[str]], rebound: frozenset[str]
) -> frozenset[int]:
    """Return the classes whose name another statement binds or deletes.

    A use of that name may mean another binding, so such a class never moves.
    """
    counts = Counter(name for found in changes for name in found)
    counts.update(rebound)
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    return frozenset(cls for cls in classes if counts[decls[cls].stmt.name] > 1)


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


def _blocked(
    decls: dict[int, Decl],
    effects: list[ImportTimeNames],
    binders: dict[int, frozenset[int]],
    kept: frozenset[int],
    bound: frozenset[str],
) -> dict[int, frozenset[int]]:
    """Return the statements each class must not move past.

    A move past a statement that binds a name it reads when defined changes
    that name. If it reads a name the scope may bind, so may any statement but
    a decl that runs no scope code, such as a call that sets it as a global.
    """
    walls = frozenset(range(len(effects))) - (decls.keys() - kept)
    classes = [idx for idx, decl in decls.items() if decl.kind is DeclKind.CLASS]
    walled = {cls for cls in classes if _reads_bound(effects[cls].loads, bound)}
    return {
        cls: binders[cls] | (walls if cls in walled else frozenset()) for cls in classes
    }


def _reads_bound(loads: set[str], bound: frozenset[str]) -> bool:
    """Report whether loads name what the scope binds; after a star import, any."""
    return bool(loads & bound) or ("*" in bound and bool(loads))


def _place(
    decls: dict[int, Decl],
    plain: _Users,
    blocked: dict[int, frozenset[int]],
    kept: frozenset[int],
) -> dict[int, Use]:
    """Return where each class without methods that can move goes.

    One that can't move stays put, so the classes it uses go above it where it
    is. Each round fixes the classes the round before couldn't move.
    """
    fixed = kept & plain.keys()
    while True:
        uses = _first_uses(decls, plain, fixed)
        movable = _movable(blocked, uses, fixed)
        stuck = frozenset(uses) - movable
        if stuck <= fixed:
            return {cls: use for cls, use in uses.items() if cls in movable}
        fixed |= stuck


def _first_uses(
    decls: dict[int, Decl], plain: _Users, fixed: frozenset[int]
) -> dict[int, Use]:
    """Return where each class without methods goes, above its first user.

    A user that is such a class and can move counts where that class goes, one
    deeper, so the deeper class sits above it.
    """
    uses: dict[int, Use] = {}
    for cls in plain:
        _resolve(decls, plain, fixed, uses, cls)
    return uses


def _resolve(
    decls: dict[int, Decl],
    plain: _Users,
    fixed: frozenset[int],
    uses: dict[int, Use],
    root: int,
) -> None:
    """Add root's use to uses, after those of the classes that use it.

    A stack, not recursion, so a long chain of such classes doesn't overflow.
    """
    pending = [root]
    while pending:
        cls = pending[-1]
        moving = [user for user in plain[cls] if user in plain and user not in fixed]
        todo = [user for user in moving if user not in uses]
        if todo:
            pending.extend(todo)
        else:
            uses[pending.pop()] = _use(decls, plain[cls], uses, fixed)


def _use(
    decls: dict[int, Decl],
    users: list[int],
    uses: dict[int, Use],
    fixed: frozenset[int],
) -> Use:
    """Return the first of users.

    A use through such a class comes before a direct use at the same place. A
    decl's place is that of its first stub.
    """
    keys = [
        (uses[user].at, 0, -uses[user].depth - 1, user)
        if user in uses and user not in fixed
        else (decls[user].first if user in decls else user, 1, 0, user)
        for user in users
    ]
    place, _, depth, user = min(keys)
    return Use(user, place, -depth)


def _movable(
    blocked: dict[int, frozenset[int]], uses: dict[int, Use], fixed: frozenset[int]
) -> frozenset[int]:
    """Return the classes that can move to their first user.

    One must not pass a statement it's blocked by, unless that is a deeper
    class moving to the same place, so deeper classes are decided first.
    """
    movable: set[int] = set()
    for cls in sorted(uses, key=lambda idx: -uses[idx].depth):
        use = uses[cls]
        passed = range(cls + 1, use.at) if cls < use.at else range(use.at, cls)
        crossed = blocked[cls].intersection(passed)
        is_movable = all(_moves_with(uses, movable, use, idx) for idx in crossed)
        if cls not in fixed and is_movable:
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
