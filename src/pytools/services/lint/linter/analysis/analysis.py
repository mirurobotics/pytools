from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    """A single lint violation."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"
