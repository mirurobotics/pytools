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
