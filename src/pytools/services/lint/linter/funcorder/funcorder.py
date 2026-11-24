import ast
from bisect import bisect_left
from itertools import accumulate

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder.decl import Decl
from pytools.services.lint.linter.funcorder.inert import is_inert_stmt
from pytools.services.lint.linter.funcorder.model import Model, build, must_precede
from pytools.services.lint.linter.funcorder.order import arrange
from pytools.services.lint.linter.funcorder.plain import place, plain_violations
from pytools.services.lint.linter.funcorder.render import has_shared_lines, render
from pytools.services.lint.linter.funcorder.walls import is_inert_decl


def check(file: CheckInput) -> list[Diagnostic]:
    """Report defs and classes out of order in the module and each class."""
    scopes = _scopes(file.tree)
    diags = [diag for scope in scopes for diag in _check_scope(file, scope)]
    return sorted(diags, key=lambda diag: diag.line)


def fix(file: CheckInput) -> str | None:
    """Return the source with each scope check reports on laid out in its order.

    Return None when no scope can move, or when the result would not hold the
    same statements.
    """
    orders: dict[ast.Module | ast.ClassDef, list[int]] = {}
    for scope in _scopes(file.tree):
        order = _fixed_order(file, scope)
        if order is not None:
            orders[scope] = order
    if not orders:
        return None
    fixed = render(file, orders)
    return fixed if _holds_same_statements(file, fixed) else None


def _fixed_order(
    file: CheckInput, scope: ast.Module | ast.ClassDef
) -> list[int] | None:
    """Return the order to lay scope out in, or None to leave it as it is.

    A scope stays when check reports nothing on it, its statements share a
    line, or the order would change what runs when it is defined.
    """
    if not _check_scope(file, scope) or has_shared_lines(file, scope):
        return None
    model = build(file, scope)
    order = place(model, arrange(model)[0])
    return order if _is_safe(scope, model, order) else None


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


def _is_safe(scope: ast.Module | ast.ClassDef, model: Model, order: list[int]) -> bool:
    """Report whether order keeps what runs when scope is defined.

    No statement moves past one that may run code, since such a statement may
    use any name above it, and each decl stays below the statements it needs.
    """
    spans = {part: decl for decl in model.decls.values() for part in decl.span}
    calm = {
        idx
        for idx, stmt in enumerate(scope.body)
        if (is_inert_decl(scope, spans[idx]) if idx in spans else is_inert_stmt(stmt))
    }
    active = sorted(set(order) - calm)
    seen = list(accumulate((int(idx not in calm) for idx in order), initial=0))
    is_kept = all(
        seen[pos] == bisect_left(active, idx) for pos, idx in enumerate(order)
    )
    rank = {idx: pos for pos, idx in enumerate(order)}
    starts = {idx: rank[decl.span.start] for idx, decl in model.decls.items()}
    needs = model.needs.items()
    is_below = all(rank[need] < starts[idx] for idx, found in needs for need in found)
    return is_kept and is_below


def _holds_same_statements(file: CheckInput, fixed: str) -> bool:
    """Report whether fixed parses to file's statements, each scope's in any order."""
    try:
        after = ast.parse(fixed)
    except SyntaxError:
        return False
    return _sorted_dump(ast.parse("\n".join(file.lines))) == _sorted_dump(after)


def _sorted_dump(tree: ast.Module) -> str:
    """Return tree dumped with each scope's statements sorted, innermost first."""
    scopes = _scopes(tree)
    for scope in reversed(scopes):
        scope.body.sort(key=ast.dump)
    return ast.dump(tree)


def _scopes(tree: ast.Module) -> list[ast.Module | ast.ClassDef]:
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return [tree, *classes]
