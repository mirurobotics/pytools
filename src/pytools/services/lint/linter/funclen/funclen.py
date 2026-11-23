import ast
from collections.abc import Iterator

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

type _Function = ast.FunctionDef | ast.AsyncFunctionDef

_LITERALS = (ast.Constant, ast.JoinedStr, ast.List, ast.Tuple, ast.Set, ast.Dict)


def check(file: CheckInput, max_len: int) -> list[Diagnostic]:
    """Report functions over max_len code lines; a multi-line literal counts as one."""
    if max_len <= 0:
        return []
    diags = [_check_function(file, func, max_len) for func in _functions(file.tree)]
    return [diag for diag in diags if diag is not None]


def _functions(tree: ast.Module) -> list[_Function]:
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return sorted(functions, key=lambda func: func.lineno)


def _check_function(
    file: CheckInput, func: _Function, max_len: int
) -> Diagnostic | None:
    count = _count_lines(func, file.lines)
    if count <= max_len:
        return None
    first = min((dec.lineno for dec in func.decorator_list), default=func.lineno)
    if has_nolint_on_lines(file.comments, Rule.FUNCLEN, first - 1, func.lineno):
        return None
    message = f"function {func.name} is {count} lines (limit {max_len})"
    return Diagnostic(file.path, func.lineno, message)


def _count_lines(func: _Function, lines: list[str]) -> int:
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    if not body:
        return 0
    skip = _literal_tail_lines(body)
    code_lines = [
        number
        for number in range(body[0].lineno, _end_line(func) + 1)
        if number not in skip and _is_code_line(lines[number - 1])
    ]
    return len(code_lines)


def _literal_tail_lines(body: list[ast.stmt]) -> set[int]:
    nodes = list(_nodes_outside_literals(body))
    literals = [node for node in nodes if isinstance(node, _LITERALS)]
    skip = {
        line for lit in literals for line in range(lit.lineno + 1, _end_line(lit) + 1)
    }
    code_starts = {getattr(node, "lineno", None) for node in nodes}
    closing_lines = {_end_line(lit) for lit in literals}
    return skip - (closing_lines & code_starts)


def _nodes_outside_literals(body: list[ast.stmt]) -> Iterator[ast.AST]:
    pending: list[ast.AST] = list(body)
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, _LITERALS):
            pending.extend(ast.iter_child_nodes(node))


def _end_line(node: ast.expr | ast.stmt) -> int:
    return node.end_lineno or node.lineno


def _is_code_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")
