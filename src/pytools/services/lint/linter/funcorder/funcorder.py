import ast
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder.decl import Decl
from pytools.services.lint.linter.funcorder.model import Model, build, must_precede
from pytools.services.lint.linter.funcorder.order import arrange
from pytools.services.lint.linter.funcorder.plain import plain_violations
from pytools.services.lint.linter.funcorder.render import has_shared_lines, render


def check(file: CheckInput) -> list[Diagnostic]:
    """Report defs and classes out of order in the module and each class."""
    diags = [
        Diagnostic(file.path, found.model.decls[idx].stmt.lineno, message)
        for found in _arrange_scopes(file)
        for idx, messages in found.misplaced.items()
        for message in messages
    ]
    return sorted(diags, key=lambda diag: diag.line)


def fix(file: CheckInput) -> str | None:
    """Return the source with each scope that check reports on in check's order.

    Return None when check reports nothing. A scope with statements that share
    a line is left as it is.
    """
    reported = [found for found in _arrange_scopes(file) if found.misplaced]
    orders = {
        found.scope: _fixed_order(found)
        for found in reported
        if not has_shared_lines(file, found.scope)
    }
    return render(file, orders) if orders else None


@dataclass(frozen=True)
class _Arranged:
    """A scope, the order check wants, and the decls check reports on."""

    scope: ast.Module | ast.ClassDef
    model: Model
    order: list[int]  # leaves out the classes placed by their first user
    misplaced: dict[int, list[str]]  # check's messages for each decl


def _arrange_scopes(file: CheckInput) -> list[_Arranged]:
    scopes: list[ast.Module | ast.ClassDef] = [file.tree, *_classes(file.tree)]
    return [_arrange_scope(file, scope) for scope in scopes]


def _classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _arrange_scope(file: CheckInput, scope: ast.Module | ast.ClassDef) -> _Arranged:
    model = build(file, scope)
    order, below = arrange(model)
    found = {
        decl.idx: _violations(model, decl, order, below)
        for decl in model.decls.values()
    }
    misplaced = {idx: messages for idx, messages in found.items() if messages}
    plain = plain_violations(model)
    misplaced.update((cls, [message]) for cls, message in plain.items())
    return _Arranged(scope, model, order, misplaced)


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


def _fixed_order(found: _Arranged) -> list[int]:
    """Return the scope's statements in check's order, classes included.

    A class placed by its first user goes directly above it when check reports
    it, and otherwise stays directly above the statement below it.
    """
    uses = found.model.classes.uses
    above: dict[int, list[int]] = {}
    for cls in sorted(uses, key=lambda idx: (-uses[idx].depth, idx)):
        target = uses[cls].at if cls in found.misplaced else cls + 1
        above.setdefault(target, []).append(cls)
    return [placed for idx in found.order for placed in _stacked(above, idx)]


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
