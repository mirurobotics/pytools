import ast
from dataclasses import dataclass
from enum import Enum, auto

from pytools.services.lint.linter.analysis.analysis import Function


class DeclKind(Enum):
    """How a decl takes part in its scope's order."""

    PUBLIC = auto()
    PRIVATE = auto()  # named with a leading underscore, and not a dunder
    EXEMPT = auto()  # a def with a nolint, which keeps its place
    CLASS = auto()  # one caller, through its methods' calls


@dataclass(frozen=True)
class Decl:
    """A def or class in a scope, one of the units the scope is ordered by."""

    idx: int
    stmt: Function | ast.ClassDef
    name: str
    kind: DeclKind
    first: int  # its first stub, such as a property getter, or idx without one
