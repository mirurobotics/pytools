import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from pytools.services.lint.linter.analysis.comments import Comment

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class Rule(StrEnum):
    """A custom linter rule name."""

    FUNCLEN = "funclen"
    FILELEN = "filelen"
    NESTDEPTH = "nestdepth"
    NAMELEN = "namelen"
    VARNAME = "varname"
    STRAYCOMMENT = "straycomment"


@dataclass(frozen=True)
class CheckInput:
    """One parsed file for the rule checks."""

    path: str
    tree: ast.Module
    lines: list[str]
    comments: dict[int, Comment]


@dataclass(frozen=True)
class Diagnostic:
    """A single lint violation."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def functions(tree: ast.Module) -> list[Function]:
    """Return every function in tree, nested ones included, in line order."""
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return sorted(found, key=lambda func: func.lineno)


def walk_outside(
    nodes: Iterable[ast.AST], stop: tuple[type[ast.AST], ...]
) -> Iterator[ast.AST]:
    """Yield nodes and their descendants depth-first, not entering stop nodes."""
    pending = list(nodes)[::-1]
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, stop):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def is_code_line(file: CheckInput, number: int) -> bool:
    """Report whether line number holds more than whitespace and a comment."""
    line = file.lines[number - 1]
    comment = file.comments.get(number)
    if comment is not None:
        line = line[: comment.column]
    return bool(line.strip())


def start_line(node: ast.stmt) -> int:
    """Return the first line of node, counting its decorators."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return min((dec.lineno for dec in node.decorator_list), default=node.lineno)
    return node.lineno


def header_end(
    file: CheckInput, node: Function | ast.ClassDef | ast.ExceptHandler
) -> int:
    """Return the last code line of node's header, the line before its body."""
    line = start_line(node.body[0]) - 1
    while line > node.lineno and not is_code_line(file, line):
        line -= 1
    return max(line, node.lineno)


def body_lines(file: CheckInput, func: Function) -> range:
    """Return the lines of func's body, after its header.

    A comment indented under the def after its last statement is still in its
    body.
    """
    end = func.end_lineno or func.lineno
    while end < len(file.lines) and _is_body_tail(file, end + 1, func.col_offset):
        end += 1
    return range(header_end(file, func) + 1, end + 1)


def _is_body_tail(file: CheckInput, number: int, indent: int) -> bool:
    if is_code_line(file, number):
        return False
    comment = file.comments.get(number)
    return comment is None or comment.column > indent


def module_header_end(file: CheckInput) -> int:
    """Return the first statement's line, or the last line of a module without one.

    Lines up to it are the module header: shebang, encoding, license and
    file-wide directives.
    """
    body = file.tree.body
    return start_line(body[0]) if body else len(file.lines)


def elif_branch(stmt: ast.If) -> ast.If | None:
    """Return the if an elif after stmt parses to, or None if stmt has none.

    An elif sits at its if's column; a block under else is indented.
    """
    branch = stmt.orelse[0] if stmt.orelse else None
    if isinstance(branch, ast.If) and branch.col_offset == stmt.col_offset:
        return branch
    return None
