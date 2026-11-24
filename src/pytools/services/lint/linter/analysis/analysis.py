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
    FUNCCOMMENT = "funccomment"
    COMMENTEDCODE = "commentedcode"
    MUTABLEGLOBAL = "mutableglobal"


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


def function_body_lines(file: CheckInput) -> set[int]:
    """Return the lines inside any function's body, after its header.

    A comment indented under a def after its last statement is still in its
    body.
    """
    bodies = [_body_lines(file, func) for func in functions(file.tree)]
    return {number for body in bodies for number in body}


def _body_lines(file: CheckInput, func: Function) -> range:
    end = func.end_lineno or func.lineno
    while end < len(file.lines) and _is_body_tail(file, end + 1, func.col_offset):
        end += 1
    return range(header_end(file, func) + 1, end + 1)


def _is_body_tail(file: CheckInput, number: int, indent: int) -> bool:
    if is_code_line(file, number):
        return False
    comment = file.comments.get(number)
    return comment is None or comment.column > indent


def header_end(
    file: CheckInput, node: Function | ast.ClassDef | ast.ExceptHandler
) -> int:
    """Return the last code line of node's header.

    A body that starts after the colon shares the header's last line.
    """
    first = node.body[0]
    if _follows_code(file, first):
        return first.lineno
    line = start_line(first) - 1
    while line > node.lineno and not is_code_line(file, line):
        line -= 1
    return line


def _follows_code(file: CheckInput, stmt: ast.stmt) -> bool:
    prefix = file.lines[stmt.lineno - 1].encode()[: stmt.col_offset]
    return bool(prefix.strip())


def is_code_line(file: CheckInput, number: int) -> bool:
    """Report whether line number holds more than whitespace and a comment."""
    line = file.lines[number - 1]
    comment = file.comments.get(number)
    if comment is not None:
        line = line[: comment.column]
    return bool(line.strip())


def functions(tree: ast.Module) -> list[Function]:
    """Return every function in tree, nested ones included, in line order."""
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return sorted(found, key=lambda func: func.lineno)


def module_header_end(file: CheckInput) -> int:
    """Return the first statement's line, or the last line of a module without one.

    Lines up to it are the module header: shebang, encoding, license and
    file-wide directives.
    """
    body = file.tree.body
    return start_line(body[0]) if body else len(file.lines)


def start_line(node: ast.stmt) -> int:
    """Return the first line of node, counting its decorators."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return min((dec.lineno for dec in node.decorator_list), default=node.lineno)
    return node.lineno


def elif_branch(stmt: ast.If) -> ast.If | None:
    """Return the if an elif after stmt parses to, or None if stmt has none.

    An elif sits at its if's column; a block under else is indented.
    """
    branch = stmt.orelse[0] if stmt.orelse else None
    if isinstance(branch, ast.If) and branch.col_offset == stmt.col_offset:
        return branch
    return None


def line_groups(lines: list[int]) -> list[list[int]]:
    """Split sorted line numbers into groups of consecutive lines."""
    groups: list[list[int]] = []
    for number in lines:
        if groups and groups[-1][-1] == number - 1:
            groups[-1].append(number)
        else:
            groups.append([number])
    return groups
