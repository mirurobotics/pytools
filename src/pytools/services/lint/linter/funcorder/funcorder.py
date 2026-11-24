import ast

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder.model import (
    Decl,
    DeclKind,
    Model,
    build,
    must_precede,
)
from pytools.services.lint.linter.funcorder.order import arrange
from pytools.services.lint.linter.funcorder.plain import plain_violations


def check(file: CheckInput) -> list[Diagnostic]:
    """Report defs and classes out of order in the module and each class."""
    scopes: list[ast.Module | ast.ClassDef] = [file.tree, *_classes(file.tree)]
    diags = [diag for scope in scopes for diag in _check_scope(file, scope)]
    return sorted(diags, key=lambda diag: diag.line)


def _classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _check_scope(
    file: CheckInput, scope: ast.Module | ast.ClassDef
) -> list[Diagnostic]:
    model = build(file, scope)
    order, below = arrange(model)
    misplaced = plain_violations(model)
    return [
        Diagnostic(file.path, decl.stmt.lineno, message)
        for decl in model.decls.values()
        for message in _violations(model, decl, order, below, misplaced)
    ]


def _violations(
    model: Model,
    decl: Decl,
    order: list[int],
    below: set[int],
    misplaced: dict[int, str],
) -> list[str]:
    if decl.kind is DeclKind.EXEMPT:
        return []
    found = [_stepdown(model, decl), _rank_order(model, decl), misplaced.get(decl.idx)]
    messages = [message for message in found if message is not None]
    if messages or decl.idx not in below:
        return messages
    return _directly_below(model, decl, order)


def _stepdown(model: Model, decl: Decl) -> str | None:
    callers = model.callers[decl.idx]
    if not callers or max(callers) < decl.idx:
        return None
    last = model.decls[max(callers)].name
    return f'"{decl.name}" should be below its last caller "{last}"'


def _rank_order(model: Model, decl: Decl) -> str | None:
    above = [other for other in model.decls.values() if other.idx < decl.idx]
    private = [other for other in above if must_precede(model, decl, other)]
    if not private:
        return None
    return f'"{decl.name}" should be above private "{private[0].name}"'


def _directly_below(model: Model, decl: Decl, order: list[int]) -> list[str]:
    """Report decl unless it sits right under the def placed above it.

    The statements it carries sit between them in both orders, and classes
    placed by their first users are passed over in both.
    """
    pos, first = order.index(decl.idx), decl.idx
    while pos > 0 and _is_passed_over(model, order[pos - 1]):
        pos -= 1
        if order[pos] not in model.plain:
            first = order[pos]
    prev = first - 1
    while prev in model.plain:
        prev -= 1
    if pos == 0 or order[pos - 1] == prev:
        return []
    above = model.decls[order[pos - 1]].name
    return [f'"{decl.name}" should be directly below "{above}"']


def _is_passed_over(model: Model, idx: int) -> bool:
    return idx not in model.decls or idx in model.plain
