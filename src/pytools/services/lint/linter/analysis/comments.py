import io
import tokenize


def collect_comments(source: str) -> dict[int, str]:
    """Map each line that holds a comment to that comment's text."""
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {
        token.start[0]: token.string
        for token in tokens
        if token.type == tokenize.COMMENT
    }
