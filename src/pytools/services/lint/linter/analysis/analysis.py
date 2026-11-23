import ast
from dataclasses import dataclass
from enum import StrEnum


class Rule(StrEnum):
    """A custom linter rule name."""

    FUNCLEN = "funclen"


@dataclass(frozen=True)
class CheckInput:
    """One parsed file for the rule checks."""

    path: str
    tree: ast.Module
    lines: list[str]
    comments: dict[int, str]


@dataclass(frozen=True)
class Diagnostic:
    """A single lint violation."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def is_code_line(line: str) -> bool:
    """Report whether line holds more than whitespace and a comment."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def start_line(node: ast.stmt) -> int:
    """Return the first line of node, counting its decorators."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return min((dec.lineno for dec in node.decorator_list), default=node.lineno)
    return node.lineno
