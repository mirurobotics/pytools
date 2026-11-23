import io
import tokenize
from dataclasses import dataclass


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
