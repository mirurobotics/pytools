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
    name_set,
    new_func_scope,
    pure_builtins,
    root_name,
    scope_imports,
)

_MIN_FIELD_ASSERTS: Final = 3

type _Block = tuple[list[ast.stmt], Bindings]
type _Pending = tuple[ast.AST, tuple[FuncScope, ...], frozenset[str]]


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
    module_imports = scope_imports(file, file.tree, frozenset())
    pure = pure_builtins(file)
    blocks: list[_Block] = []
    pending: list[_Pending] = [(file.tree, (), module_imports)]
    while pending:
        node, scopes, imports = pending.pop()
        if isinstance(node, DEFS):
            scopes, imports = (*scopes, new_func_scope(file, node)), module_imports
        elif isinstance(node, ast.ClassDef):
            imports = scope_imports(file, node, module_imports)
        lists = [part for _, part in ast.iter_fields(node) if _is_stmt_list(part)]
        blocks.extend((stmts, Bindings(scopes, imports, pure)) for stmts in lists)
        pending.extend((child, scopes, imports) for child in ast.iter_child_nodes(node))
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
    pure = bindings.pure_builtins
    for stmt in stmts:
        attr = _field(stmt, bindings)
        base = None if attr is None else _base_text(attr)
        changed = changed_names(stmt, pure)
        unchecked = changed if attr is None else _unchecked_changes(stmt, attr, pure)
        open_groups = _close_changed(open_groups, base, unchecked, changed)
        if (
            attr is None
            or base is None
            or not name_set(attr.value).isdisjoint(unchecked)
        ):
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


def _base_text(attr: ast.Attribute) -> str | None:
    """Return the value attr reads as text, or None if too deep to unparse."""
    try:
        return ast.unparse(attr.value)
    except RecursionError:
        return None


def _unchecked_changes(
    stmt: ast.stmt, attr: ast.Attribute, pure: frozenset[str]
) -> frozenset[str]:
    """Return the names a field assert may change outside the field attr it checks."""
    if not isinstance(stmt, ast.Assert):
        return changed_names(stmt, pure)
    parts = [part for part in ast.iter_child_nodes(stmt.test) if part is not attr]
    return frozenset(name for part in parts for name in changed_names(part, pure))


def _close_changed(
    open_groups: dict[str, _Group],
    base: str | None,
    unchecked: frozenset[str],
    changed: frozenset[str],
) -> dict[str, _Group]:
    """Return the groups that stay open: those that share no name with changed.

    A field's own base group closes only on unchecked, so build().a keeps its group.
    """
    return {
        key: group
        for key, group in open_groups.items()
        if group.deps.isdisjoint(unchecked if key == base else changed)
    }


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
