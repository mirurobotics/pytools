import ast
import io
import textwrap
import tokenize
import warnings
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
    Rule,
    is_code_line,
    line_groups,
)
from pytools.services.lint.linter.analysis.comments import is_directive
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

_MESSAGE = "commented-out code; delete it instead"
_CODE_EXPRS = (ast.Call, ast.Await, ast.Yield, ast.YieldFrom)
_NOT_CODE = (ast.Pass, ast.Break, ast.Continue, ast.Global, ast.Nonlocal)


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    is_indented: bool


def check(file: CheckInput) -> list[Diagnostic]:
    """Report comment groups that hold Python code which has been commented out."""
    numbers = sorted(file.comments)
    own_lines = [number for number in numbers if not is_code_line(file, number)]
    groups = [group for group in line_groups(own_lines) if not _has_nolint(file, group)]
    found = [_find_code(file, group) for group in groups]
    return [Diagnostic(file.path, line, _MESSAGE) for line in found if line is not None]


def _has_nolint(file: CheckInput, group: list[int]) -> bool:
    return has_nolint_on_lines(file.comments, Rule.COMMENTEDCODE, group[0], group[-1])


def _find_code(file: CheckInput, group: list[int]) -> int | None:
    for run in _runs(file, group):
        if _is_code("\n".join(line.text for line in run)):
            return _first_non_blank(run)
        line = _code_line(run)
        if line is not None:
            return line
    return None


def _runs(file: CheckInput, group: list[int]) -> list[list[_Line]]:
    """Split group at its directives, which are never code."""
    runs: list[list[_Line]] = [[]]
    for number in group:
        text = file.comments[number].text
        if is_directive(text):
            runs.append([])
        else:
            runs[-1].append(_line(number, text))
    return [run for run in runs if run]


def _line(number: int, comment: str) -> _Line:
    body = comment.removeprefix("#")
    is_indented = body.startswith(("\t", "  "))
    return _Line(number, body.removeprefix(" "), is_indented)


def _is_code(text: str) -> bool:
    source = textwrap.dedent(text)
    tree = _parse(source)
    if tree is None or _has_spaced_dot(source, tree) or _has_non_ascii_name(source):
        return False
    exempt = _exempt_stmts(tree)
    stmts = [node for node in ast.walk(tree) if isinstance(node, ast.stmt)]
    if not all(stmt in exempt or _is_plausible(stmt) for stmt in stmts):
        return False
    return any(not isinstance(stmt, _NOT_CODE) for stmt in stmts)


def _parse(source: str) -> ast.Module | None:
    """Parse source, or return None if it is not Python.

    Prose that parses can raise warnings, such as invalid escapes, that are
    not the user's to fix.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(source)
    except SyntaxError:
        return None


def _has_spaced_dot(source: str, tree: ast.Module) -> bool:
    """Report whether an attribute has a space at its dot, as in "e.g. Close()"."""
    lines = source.encode().split(b"\n")
    attributes = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    return any(_is_spaced(lines, attribute) for attribute in attributes)


def _is_spaced(lines: list[bytes], attribute: ast.Attribute) -> bool:
    """Report whether a space sits between attribute's value and name on one line.

    A gap that spans lines is a wrapped call chain.
    """
    end_line = attribute.end_lineno
    if end_line is None or attribute.value.end_lineno != end_line:
        return False
    name_start = (attribute.end_col_offset or 0) - len(attribute.attr.encode())
    gap = lines[end_line - 1][attribute.value.end_col_offset : name_start]
    return b" " in gap or b"\t" in gap


def _has_non_ascii_name(source: str) -> bool:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    names = [token.string for token in tokens if token.type == tokenize.NAME]
    return not all(name.isascii() for name in names)


def _exempt_stmts(tree: ast.Module) -> set[ast.stmt]:
    """Return the docstrings and class fields in tree.

    Each would read as prose on its own, but is code where it sits.
    """
    scopes: list[Function | ast.ClassDef] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    docstrings = {
        scope.body[0] for scope in scopes if ast.get_docstring(scope) is not None
    }
    fields = {
        stmt
        for scope in scopes
        if isinstance(scope, ast.ClassDef)
        for stmt in scope.body
        if isinstance(stmt, ast.AnnAssign)
    }
    return docstrings | fields


def _is_plausible(stmt: ast.stmt) -> bool:
    """Report whether stmt reads as code rather than prose that parses.

    A bare annotation reads as a "Note: text" label, and an expression
    statement other than a call as a phrase.
    """
    if isinstance(stmt, ast.AnnAssign):
        return stmt.value is not None
    if isinstance(stmt, ast.Expr):
        return isinstance(stmt.value, _CODE_EXPRS)
    return True


def _first_non_blank(run: list[_Line]) -> int:
    lines = (line.number for line in run[:-1] if line.text.strip())
    return next(lines, run[-1].number)


def _code_line(run: list[_Line]) -> int | None:
    """Return the first unindented line that is code on its own.

    A lone line was already checked as its run; indented lines are examples
    under prose.
    """
    if len(run) == 1:
        return None
    lines = (line for line in run if not line.is_indented)
    code = (line.number for line in lines if _is_code(line.text))
    return next(code, None)
