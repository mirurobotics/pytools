import ast
from dataclasses import dataclass
from enum import StrEnum

from pytools.services.lint.linter.analysis.comments import Comment

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class Rule(StrEnum):
    """A custom linter rule name."""

    FUNCLEN = "funclen"
    FILELEN = "filelen"


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
