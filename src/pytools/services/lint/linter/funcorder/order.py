from pytools.services.lint.linter.funcorder.model import Model, must_precede


def arrange(model: Model) -> tuple[list[int], set[int]]:
    """Return the scope's statements in order and the defs placed under a caller.

    A statement directly above a def or class moves with it, unless that would
    reorder statements, which run in order at import time.
    """
    order, below = _arrange(model, settled=False)
    if _keeps_statement_order(model, order):
        return order, below
    return _arrange(model, settled=True)


def _arrange(model: Model, *, settled: bool) -> tuple[list[int], set[int]]:
    units = {unit[-1]: unit for unit in _units(model, settled=settled)}
    left = list(units)
    stack: list[int] = []
    done: set[int] = set()
    order: list[int] = []
    below: set[int] = set()
    while left:
        key, is_below = _pick(model, left, stack, done)
        left.remove(key)
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
    units: list[list[int]] = []
    pending: list[int] = []
    for idx in range(len(model.stmts)):
        if idx in model.decls:
            units.append([*pending, idx])
            pending = []
        elif idx in model.stubs or (idx > first and not settled):
            pending.append(idx)
        else:
            units.extend([held] for held in [*pending, idx])
            pending = []
    units.extend([held] for held in pending)
    return units


def _pick(
    model: Model, left: list[int], stack: list[int], done: set[int]
) -> tuple[int, bool]:
    """Return the next unit, and whether it goes directly under a caller.

    The walk follows calls depth-first. When no call leads on, it takes the
    first unit left that is ready, or the first left if none is.
    """
    while stack:
        calls = model.calls.get(stack[-1], [])
        found = [key for key in calls if key in left and _is_ready(model, key, done)]
        if found:
            return found[0], True
        stack.pop()
    ready = [key for key in left if _is_ready(model, key, done)]
    return (ready or left)[0], False


def _is_ready(model: Model, idx: int, done: set[int]) -> bool:
    """Report whether the unit ending at idx can be placed next.

    A def waits for its callers, a waiting cycle member for one cycle caller,
    and a private def nothing calls for the public ones nothing calls.
    """
    decl = model.decls.get(idx)
    if decl is None or decl.exempt:
        return True
    if not done.issuperset(model.callers[idx]):
        return False
    if idx in model.waiting and done.isdisjoint(model.cycle_callers[idx]):
        return False
    return all(
        other.idx in done
        for other in model.decls.values()
        if must_precede(model, other, decl)
    )


def _keeps_statement_order(model: Model, order: list[int]) -> bool:
    held = [idx for idx in order if idx not in model.decls and idx not in model.stubs]
    return held == sorted(held)
