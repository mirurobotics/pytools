import io
import re
import tokenize
from dataclasses import dataclass
from typing import Final

_DIRECTIVE: Final = (
    r"#\s*(?:(?i:noqa)\b|nosec\b"
    r"|(?:type|nolint|pragma|fmt|isort|mypy|ruff|pylint|pyright):)"
)


@dataclass(frozen=True)
class Comment:
    """A comment and the column it starts at."""

    column: int
    text: str


def collect_comments(source: str) -> dict[int, Comment]:
    """Map each line that holds a comment to that comment."""
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {
        token.start[0]: Comment(token.start[1], token.string)
        for token in tokens
        if token.type == tokenize.COMMENT
    }


def is_directive(text: str) -> bool:
    """Report whether a comment is a tool directive such as # noqa."""
    return re.match(_DIRECTIVE, text) is not None
