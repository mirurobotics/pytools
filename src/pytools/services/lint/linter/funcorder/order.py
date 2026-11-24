from pytools.services.lint.linter.funcorder.model import Model, must_precede
from pytools.services.lint.linter.funcorder.tuck import tuck


def arrange(model: Model) -> tuple[list[int], set[int]]:
    """Return the scope's statements in order, and those placed under a caller.

    The second holds each def placed directly under a caller, with the
    statements it carries, and each class tucked under its users. A statement
    directly above a def or class moves with it, unless that would reorder
    statements, which run in order at import time, or a later def or class uses
    it when defined. Each class without methods that can move to its first user
    is left out, since it goes directly above that user.
    """
    decls = model.decls
    blockers = {
        idx: {other for other in decls if must_precede(model, decls[other], decl)}
        for idx, decl in decls.items()
    }
    order, below = _arrange(model, blockers, settled=False)
    if _keeps_statement_order(model, order):
        return order, below
    return _arrange(model, blockers, settled=True)


def _arrange(
    model: Model, blockers: dict[int, set[int]], *, settled: bool
) -> tuple[list[int], set[int]]:
    units = {unit[-1]: unit for unit in _units(model, settled=settled)}
    inherited = {idx: _inherited_needs(model, units[idx]) for idx in model.decls}
    needs = {
        idx: blockers[idx] | model.needs[idx] | inherited[idx] for idx in model.decls
    }
    waits = {
        idx: _placed(model, found) - set(units[idx]) for idx, found in needs.items()
    }
    left = dict.fromkeys(key for key in units if key not in model.classes.uses)
    stack: list[int] = []
    done = set(model.classes.uses)
    trees: list[list[int]] = []
    below: set[int] = set()
    while left:
        key, is_below = _pick(model, left, stack, done, waits)
        del left[key]
        stack.append(key)
        done.update(units[key])
        if is_below:
            below.update(units[key])
            trees[-1].extend(units[key])
        else:
            trees.append(list(units[key]))
    below |= tuck(model, trees, waits)
    return [idx for tree in trees for idx in tree], below


def _units(model: Model, *, settled: bool) -> list[list[int]]:
    """Split the scope into each def or class with the statements it carries.

    A statement no def or class carries is a unit of its own, and so is each
    statement above the first def or class: the header never moves. A class
    without methods that can move to its first user moves there alone, so the
    statements above it go with the next def or class.
    """
    first = min(model.decls, default=0)
    anchored = _anchored(model)
    units: list[list[int]] = []
    pending: list[int] = []
    for idx in range(len(model.stmts)):
        is_carried = idx > first and not settled and idx not in anchored
        if idx in model.classes.uses:
            units.append([idx])
        elif idx in model.decls:
            units.append([*pending, idx])
            pending = []
        elif idx in model.stubs or is_carried:
            pending.append(idx)
        else:
            units.extend([held] for held in [*pending, idx])
            pending = []
    units.extend([held] for held in pending)
    return units


def _anchored(model: Model) -> set[int]:
    """Return the statements a decl below the one that would carry them uses.

    Carrying such a statement could move it past that use, so it stays put.
    """
    return {
        stmt
        for idx, needed in model.needs.items()
        for stmt in needed
        if any(stmt < other < idx for other in model.decls)
    }


def _inherited_needs(model: Model, unit: list[int]) -> set[int]:
    """Return what the classes without methods unit uses need when defined.

    One that can't move stays put, so no user waits for it.
    """
    inherited = model.classes.inherited
    return {need for idx in unit for need in inherited.get(idx, frozenset())}


def _placed(model: Model, needs: set[int]) -> set[int]:
    """Return where needs end up: a class that moves goes above its first user."""
    uses = model.classes.uses
    return {uses[need].at if need in uses else need for need in needs}


def _pick(
    model: Model,
    left: dict[int, None],
    stack: list[int],
    done: set[int],
    waits: dict[int, set[int]],
) -> tuple[int, bool]:
    """Return the next unit, and whether it goes directly under a caller.

    The walk follows calls depth-first. When no call leads on, it takes the
    first unit left that is ready, or the first left if none is.
    """
    while stack:
        calls = model.calls.get(stack[-1], [])
        found = [
            key for key in calls if key in left and _is_ready(model, key, done, waits)
        ]
        if found:
            return found[0], True
        stack.pop()
    ready = (key for key in left if _is_ready(model, key, done, waits))
    return next(ready, next(iter(left))), False


def _is_ready(
    model: Model, idx: int, done: set[int], waits: dict[int, set[int]]
) -> bool:
    """Report whether the unit ending at idx can be placed next.

    A def waits for its callers, a waiting cycle member for one cycle caller,
    a private def nothing calls for the public ones nothing calls, and a decl
    for the statements it uses when defined.
    """
    decl = model.decls.get(idx)
    if decl is None or decl.exempt:
        return True
    if not done.issuperset(model.callers[idx]):
        return False
    if idx in model.waiting and done.isdisjoint(model.cycle_callers[idx]):
        return False
    return done.issuperset(waits[idx])


def _keeps_statement_order(model: Model, order: list[int]) -> bool:
    held = [idx for idx in order if idx not in model.decls and idx not in model.stubs]
    return held == sorted(held)
