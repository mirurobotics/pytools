import ast

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.funcorder.model import (
    Model,
    Node,
    build,
    must_precede,
)
from pytools.services.lint.linter.funcorder.order import arrange


def check(file: CheckInput) -> list[Diagnostic]:
    """Report defs out of control-flow order in the module and each class."""
    scopes = [file.tree, *_classes(file.tree)]
    diags = [diag for scope in scopes for diag in _check_scope(file, scope)]
    return sorted(diags, key=lambda diag: diag.line)


def _classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _check_scope(
    file: CheckInput, scope: ast.Module | ast.ClassDef
) -> list[Diagnostic]:
    model = build(file, scope)
    order, below = arrange(model)
    return [
        Diagnostic(file.path, node.stmt.lineno, message)
        for node in model.nodes.values()
        for message in _violations(model, node, order, below)
    ]


def _violations(
    model: Model, node: Node, order: list[int], below: set[int]
) -> list[str]:
    if node.exempt:
        return []
    found = [_stepdown(model, node), _rank_order(model, node)]
    messages = [message for message in found if message is not None]
    if messages or node.idx not in below:
        return messages
    return _directly_below(model, node, order)


def _stepdown(model: Model, node: Node) -> str | None:
    callers = model.callers[node.idx]
    if not callers or max(callers) < node.idx:
        return None
    last = model.nodes[max(callers)].name
    return f'"{node.name}" should be below its last caller "{last}"'


def _rank_order(model: Model, node: Node) -> str | None:
    above = [other for other in model.nodes.values() if other.idx < node.idx]
    private = [other for other in above if must_precede(model, node, other)]
    if not private:
        return None
    return f'"{node.name}" should be above private "{private[0].name}"'


def _directly_below(model: Model, node: Node, order: list[int]) -> list[str]:
    """Report node unless it sits right under the def placed above it.

    The statements it carries sit between them in both orders.
    """
    pos = order.index(node.idx)
    while pos > 0 and order[pos - 1] not in model.nodes:
        pos -= 1
    if pos == 0 or order[pos - 1] == order[pos] - 1:
        return []
    above = model.nodes[order[pos - 1]].name
    return [f'"{node.name}" should be directly below "{above}"']
