from pytools.services.lint.linter.funcorder.classes import Use
from pytools.services.lint.linter.funcorder.model import Model


def place(model: Model, order: list[int]) -> list[int]:
    """Return order with each class without methods that can move put back in.

    Each goes directly above its first user in order, deeper ones above it. One
    plain_violations passes over keeps its place while that holds there.
    """
    uses = model.classes.uses
    rank = {idx: pos for pos, idx in enumerate(order)}
    starts = {idx: decl.span.start for idx, decl in model.decls.items()}
    places = {idx: rank[starts.get(idx, idx)] for idx in order}
    found = model.classes.first_uses(places)
    above: dict[int, list[int]] = {}
    for cls in sorted(found, key=lambda idx: (-found[idx].depth, idx)):
        is_kept = found[cls].user == uses[cls].user and _stays_near(model, cls, rank)
        target = cls + 1 if is_kept else order[found[cls].at]
        above.setdefault(target, []).append(cls)
    return [placed for idx in order for placed in _stacked(above, idx)]


def _stays_near(model: Model, cls: int, rank: dict[int, int]) -> bool:
    """Report whether cls is near its first user and what lies between stays so."""
    if not _is_near(model, cls):
        return False
    user = model.classes.uses[cls].at
    between = [idx for idx in range(cls + 1, user + 1) if idx in rank]
    expected = range(rank[between[0]], rank[user] + 1)
    return [rank[idx] for idx in between] == list(expected)


def _stacked(above: dict[int, list[int]], idx: int) -> list[int]:
    """Return idx below the classes that go above it, each below its own.

    A stack, not recursion, so a long chain of such classes doesn't overflow.
    """
    found: list[int] = []
    pending = [idx]
    while pending:
        top = pending.pop()
        found.append(top)
        pending.extend(above.get(top, []))
    return found[::-1]


def plain_violations(model: Model) -> dict[int, str]:
    """Report each class without methods not directly above its first user.

    Statements may sit between them, and so may other such classes placed above
    the same user, as deep or less. A class is left alone when it has a nolint,
    its definition may run code from the scope, its name is bound again, or the
    move would pass a statement that could change what it reads when defined.
    """
    uses = model.classes.uses
    return {
        cls: _message(model, cls, uses[cls])
        for cls in sorted(uses)
        if not _is_near(model, cls)
    }


def _message(model: Model, cls: int, use: Use) -> str:
    name = model.decls[cls].name
    if use.user in model.decls:
        user = model.decls[use.user].name
        return f'class "{name}" should be directly above its first user "{user}"'
    line = model.stmts[use.user].lineno
    return f'class "{name}" should be directly above its first user on line {line}'


def _is_near(model: Model, cls: int) -> bool:
    use = model.classes.uses[cls]
    between = range(cls + 1, use.at)
    return cls < use.at and all(_may_sit_between(model, use, idx) for idx in between)


def _may_sit_between(model: Model, use: Use, idx: int) -> bool:
    if idx not in model.decls:
        return True
    other = model.classes.uses.get(idx)
    return other is not None and other.at == use.at and other.depth <= use.depth
