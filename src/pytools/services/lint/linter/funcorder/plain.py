from dataclasses import dataclass

from pytools.services.lint.linter.funcorder.model import Model


def plain_violations(model: Model) -> dict[int, str]:
    """Report each class without methods not directly above its first user.

    Statements may sit between them, and so may other such classes placed above
    the same user, as deep or less. A class that would rise past a statement it
    uses when defined is left alone, since that move raises NameError.
    """
    uses = _first_uses(model)
    movable = _movable(model, uses)
    return {
        cls: _message(model, cls, use)
        for cls, use in uses.items()
        if cls in movable and not _is_near(model, uses, cls)
    }


@dataclass(frozen=True)
class _Use:
    """Where a class without methods goes: directly above its first user."""

    user: int
    at: int  # the place of that user, or of the class it goes above
    depth: int  # how many such classes it goes above, one the user of the next


def _first_uses(model: Model) -> dict[int, _Use]:
    """Return where each class without methods goes, above its first user.

    A user that is such a class counts where that class goes, one deeper, so
    the deeper class sits above it.
    """
    uses: dict[int, _Use] = {}
    for cls in model.plain:
        _resolve(model, uses, cls)
    return uses


def _resolve(model: Model, uses: dict[int, _Use], root: int) -> None:
    """Add root's use to uses, after those of the classes that use it.

    A stack, not recursion, so a long chain of such classes doesn't overflow.
    """
    pending = [root]
    while pending:
        cls = pending[-1]
        users = model.plain[cls]
        todo = [user for user in users if user in model.plain and user not in uses]
        if todo:
            pending.extend(todo)
        else:
            uses[pending.pop()] = _use(model, uses, cls)


def _use(model: Model, uses: dict[int, _Use], cls: int) -> _Use:
    """Return cls's first use.

    A use through such a class comes before a direct use at the same place. A
    decl's place is that of its first stub.
    """
    keys = [
        (uses[user].at, 0, -uses[user].depth - 1, user)
        if user in model.plain
        else (model.decls[user].first if user in model.decls else user, 1, 0, user)
        for user in model.plain[cls]
    ]
    place, _, depth, user = min(keys)
    return _Use(user, place, -depth)


def _movable(model: Model, uses: dict[int, _Use]) -> set[int]:
    """Return the classes that can move to their first user.

    One that rises must not pass a statement it uses when defined, unless that
    is a deeper class rising with it, so deeper classes are decided first.
    """
    movable: set[int] = set()
    for cls in sorted(uses, key=lambda idx: -uses[idx].depth):
        needs = model.needs[cls]
        if all(_stays_above(uses, movable, uses[cls], need) for need in needs):
            movable.add(cls)
    return movable


def _stays_above(
    uses: dict[int, _Use], movable: set[int], use: _Use, need: int
) -> bool:
    if need < use.at:
        return True
    other = uses.get(need)
    is_deeper = other is not None and other.at == use.at and other.depth > use.depth
    return is_deeper and need in movable


def _message(model: Model, cls: int, use: _Use) -> str:
    name = model.decls[cls].name
    if use.user in model.decls:
        user = model.decls[use.user].name
        return f'class "{name}" should be directly above its first user "{user}"'
    line = model.stmts[use.user].lineno
    return f'class "{name}" should be directly above its first user on line {line}'


def _is_near(model: Model, uses: dict[int, _Use], cls: int) -> bool:
    use = uses[cls]
    between = range(cls + 1, use.at)
    return cls < use.at and all(
        _may_sit_between(model, uses, use, idx) for idx in between
    )


def _may_sit_between(
    model: Model, uses: dict[int, _Use], use: _Use, idx: int
) -> bool:
    if idx not in model.decls:
        return True
    other = uses.get(idx)
    return other is not None and other.at == use.at and other.depth <= use.depth
