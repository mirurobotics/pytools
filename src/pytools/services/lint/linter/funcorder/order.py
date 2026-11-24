from pytools.services.lint.linter.funcorder.model import DeclKind, Model, must_precede


def arrange(model: Model) -> tuple[list[int], set[int]]:
    """Return the scope's statements in order, and those placed under a caller.

    The second holds each def placed directly under a caller, with the
    statements it carries. A statement directly above a def or class moves with
    it, unless that would reorder statements, which run in order at import time,
    or a later def or class uses it when defined.
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
    waits = {
        idx: (blockers[idx] | model.needs[idx]) - set(units[idx]) for idx in model.decls
    }
    left = dict.fromkeys(units)
    stack: list[int] = []
    done: set[int] = set()
    order: list[int] = []
    below: set[int] = set()
    while left:
        key, is_below = _pick(model, left, stack, done, waits)
        del left[key]
        stack.append(key)
        done.update(units[key])
        order.extend(units[key])
        if is_below:
            below.update(units[key])
    return order, below


def _units(model: Model, *, settled: bool) -> list[list[int]]:
    """Split the scope into each def or class with the statements it carries.

    A statement no def or class carries is a unit of its own, and so is each
    statement above the first def or class: the header never moves.
    """
    first = min(model.decls, default=0)
    anchored = _anchored(model)
    units: list[list[int]] = []
    pending: list[int] = []
    for idx in range(len(model.stmts)):
        is_carried = idx > first and not settled and idx not in anchored
        if idx in model.decls:
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
    if decl is None or decl.kind is DeclKind.EXEMPT:
        return True
    if not done.issuperset(model.callers[idx]):
        return False
    if idx in model.waiting and done.isdisjoint(model.cycle_callers[idx]):
        return False
    return done.issuperset(waits[idx])


def _keeps_statement_order(model: Model, order: list[int]) -> bool:
    held = [idx for idx in order if idx not in model.decls and idx not in model.stubs]
    return held == sorted(held)
