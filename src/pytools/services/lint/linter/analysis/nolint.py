import re

from pytools.services.lint.linter.analysis.analysis import Rule

_NOLINT = re.compile(r"#\s*nolint:([^#]*)")


def has_nolint_on_lines(
    comments: dict[int, str], rule: Rule, first: int, last: int
) -> bool:
    """Report whether a nolint comment naming rule sits on a line in [first, last]."""
    return any(
        _is_nolint_for(comments.get(number, ""), rule)
        for number in range(first, last + 1)
    )


def _is_nolint_for(comment: str, rule: Rule) -> bool:
    match = _NOLINT.search(comment)
    if match is None:
        return False
    entries = (entry.split() for entry in match.group(1).split(","))
    return any(words[0] == rule for words in entries if words)
