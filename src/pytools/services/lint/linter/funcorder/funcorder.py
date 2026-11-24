import ast

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder.decl import Decl
from pytools.services.lint.linter.funcorder.model import Model, build, must_precede
from pytools.services.lint.linter.funcorder.order import arrange
from pytools.services.lint.linter.funcorder.plain import place, plain_violations
from pytools.services.lint.linter.funcorder.render import has_shared_lines, render


def check(file: CheckInput) -> list[Diagnostic]:
    """Report defs and classes out of order in the module and each class."""
    scopes = _scopes(file.tree)
    diags = [diag for scope in scopes for diag in _check_scope(file, scope)]
    return sorted(diags, key=lambda diag: diag.line)


def fix(file: CheckInput) -> str | None:
    """Return the source with each scope check reports on laid out in its order.

    Return None when check reports nothing. A scope with statements that share
    a line is left as it is.
    """
    orders: dict[ast.Module | ast.ClassDef, list[int]] = {}
    for scope in _scopes(file.tree):
        if _check_scope(file, scope) and not has_shared_lines(file, scope):
            orders[scope] = _fixed_order(file, scope)
    return render(file, orders) if orders else None


def _scopes(tree: ast.Module) -> list[ast.Module | ast.ClassDef]:
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return [tree, *classes]


def _check_scope(
    file: CheckInput, scope: ast.Module | ast.ClassDef
) -> list[Diagnostic]:
    model = build(file, scope)
    order, below = arrange(model)
    diags = [
        Diagnostic(file.path, decl.stmt.lineno, message)
        for decl in model.decls.values()
        for message in _violations(model, decl, order, below)
    ]
    diags.extend(
        Diagnostic(file.path, model.decls[cls].stmt.lineno, message)
        for cls, message in plain_violations(model).items()
    )
    return diags


def _violations(
    model: Model, decl: Decl, order: list[int], below: set[int]
) -> list[str]:
    if decl.exempt:
        return []
    found = [_stepdown(model, decl), _rank_order(model, decl)]
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
    placed by their first users, which the order leaves out, are passed over.
    """
    pos = order.index(decl.idx)
    while pos > 0 and order[pos - 1] not in model.decls:
        pos -= 1
    prev = order[pos] - 1
    while prev in model.classes.uses:
        prev -= 1
    if pos == 0 or order[pos - 1] == prev:
        return []
    above = model.decls[order[pos - 1]].name
    return [f'"{decl.name}" should be directly below "{above}"']


def _fixed_order(file: CheckInput, scope: ast.Module | ast.ClassDef) -> list[int]:
    model = build(file, scope)
    order, _ = arrange(model)
    return place(model, order)
