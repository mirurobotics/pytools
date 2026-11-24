from pytools.services.lint.linter.funcorder.classes import Use
from pytools.services.lint.linter.funcorder.model import Model


def plain_violations(model: Model) -> dict[int, str]:
    """Report each class without methods not directly above its first user.

    Statements may sit between them, and so may other such classes placed above
    the same user, as deep or less. A class that would rise past a statement it
    uses when defined is left alone, since that move raises NameError, and so is
    one whose definition may run code from the scope or whose name is rebound.
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
