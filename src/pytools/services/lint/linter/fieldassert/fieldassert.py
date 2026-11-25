import ast
from dataclasses import dataclass, field
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    DEFS,
    CheckInput,
    Diagnostic,
    Rule,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines
from pytools.services.lint.linter.fieldassert.scope import (
    Bindings,
    FuncScope,
    changed_names,
    import_names,
    name_set,
    new_func_scope,
    root_name,
)

_MIN_FIELD_ASSERTS: Final = 3

type _Block = tuple[list[ast.stmt], Bindings]


def check(file: CheckInput) -> list[Diagnostic]:
    """Report runs of asserts that compare one value field by field."""
    diags = [
        diag
        for stmts, bindings in _blocks(file)
        for diag in _check_block(file, stmts, bindings)
    ]
    return sorted(diags, key=lambda diag: diag.line)


def _blocks(file: CheckInput) -> list[_Block]:
    """Return each list of statements in file, with where its names are bound."""
    imports = import_names(file.tree.body)
    blocks: list[_Block] = []
    pending: list[tuple[ast.AST, tuple[FuncScope, ...]]] = [(file.tree, ())]
    while pending:
        node, scopes = pending.pop()
        if isinstance(node, DEFS):
            scopes = (*scopes, new_func_scope(file, node))
        lists = [part for _, part in ast.iter_fields(node) if _is_stmt_list(part)]
        blocks.extend((stmts, Bindings(scopes, imports)) for stmts in lists)
        pending.extend((child, scopes) for child in ast.iter_child_nodes(node))
    return blocks


def _is_stmt_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and isinstance(value[0], ast.stmt)


@dataclass
class _Group:
    """Asserts in one block on fields of one value, with no change between them."""

    base: str
    root: str | None
    deps: frozenset[str]
    asserts: list[ast.stmt] = field(default_factory=list)
    fields: set[str] = field(default_factory=set)


def _check_block(
    file: CheckInput, stmts: list[ast.stmt], bindings: Bindings
) -> list[Diagnostic]:
    groups: list[_Group] = []
    open_groups: dict[str, _Group] = {}
    for stmt in stmts:
        attr = _field(stmt, bindings)
        open_groups = _close_changed(open_groups, stmt, attr)
        base = None if attr is None else _base_text(attr)
        if attr is None or base is None:
            continue
        group = open_groups.get(base)
        if group is None:
            root = root_name(attr.value, bindings)
            group = _Group(base, root, name_set(attr.value))
            open_groups[base] = group
            groups.append(group)
        group.asserts.append(stmt)
        group.fields.add(attr.attr)
    wide = [group for group in groups if len(group.fields) >= _MIN_FIELD_ASSERTS]
    diags = [
        _report(file, group)
        for group in wide
        if not bindings.is_helper_param(group.root)
    ]
    return [diag for diag in diags if diag is not None]


def _field(stmt: ast.stmt, bindings: Bindings) -> ast.Attribute | None:
    """Return the field an assert a == b checks: a, or b when a is a constant."""
    compared = _compared(stmt)
    if compared is None:
        return None
    actual, expected = compared
    found = _as_field(actual, bindings)
    if found is not None or not _is_constant(actual, bindings):
        return found
    return _as_field(expected, bindings)


def _compared(stmt: ast.stmt) -> tuple[ast.expr, ast.expr] | None:
    test = stmt.test if isinstance(stmt, ast.Assert) else None
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.Eq):
        return None
    return test.left, test.comparators[0]


def _as_field(expr: ast.expr, bindings: Bindings) -> ast.Attribute | None:
    if not isinstance(expr, ast.Attribute) or bindings.is_pkg(expr.value):
        return None
    return expr


def _is_constant(expr: ast.expr, bindings: Bindings) -> bool:
    """Report whether expr is a literal or a constant from an import.

    A stack, not recursion, so deep nesting doesn't overflow.
    """
    pending = [expr]
    while pending:
        parts = _constant_parts(pending.pop(), bindings)
        if parts is None:
            return False
        pending.extend(parts)
    return True


def _constant_parts(expr: ast.expr, bindings: Bindings) -> list[ast.expr] | None:
    """Return the subexpressions expr is constant through, or None if it never is."""
    if isinstance(expr, ast.Constant):
        return []
    if isinstance(expr, ast.Attribute):
        return [] if bindings.is_pkg(expr.value) else None
    if isinstance(expr, ast.UnaryOp):
        return [expr.operand]
    if isinstance(expr, ast.List | ast.Tuple | ast.Set):
        return expr.elts
    if isinstance(expr, ast.Dict):
        keys = [key for key in expr.keys if key is not None]
        return [*keys, *expr.values]
    return None


def _close_changed(
    open_groups: dict[str, _Group], stmt: ast.stmt, attr: ast.Attribute | None
) -> dict[str, _Group]:
    """Return the groups that stay open: those whose value stmt can't change.

    The field attr an assert checks is left out, so build().a keeps its group.
    """
    changed = {name for part in _unchecked(stmt, attr) for name in changed_names(part)}
    return {
        base: group
        for base, group in open_groups.items()
        if group.deps.isdisjoint(changed)
    }


def _unchecked(stmt: ast.stmt, attr: ast.Attribute | None) -> list[ast.AST]:
    if attr is None or not isinstance(stmt, ast.Assert):
        return [stmt]
    parts = [*ast.iter_child_nodes(stmt.test), stmt.msg]
    return [part for part in parts if part is not None and part is not attr]


def _base_text(attr: ast.Attribute) -> str | None:
    """Return the value attr reads as text, or None if too deep to unparse."""
    try:
        return ast.unparse(attr.value)
    except RecursionError:
        return None


def _report(file: CheckInput, group: _Group) -> Diagnostic | None:
    first = group.asserts[0].lineno
    last = group.asserts[-1].end_lineno or first
    if has_nolint_on_lines(file.comments, Rule.FIELDASSERT, first, last):
        return None
    message = (
        f"{len(group.asserts)} asserts compare fields of {group.base} one at a"
        " time; compare the whole value in one assert"
    )
    if group.root is not None:
        message += f", or move the checks into a helper that takes {group.root}"
    return Diagnostic(file.path, first, message)
