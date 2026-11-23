import re

_NOLINT = re.compile(r"#\s*nolint:([^#]*)")


def has_nolint_on_lines(lines: list[str], rule: str, first: int, last: int) -> bool:
    """Report whether a nolint comment naming rule sits on a line in [first, last]."""
    numbers = range(max(first, 1), min(last, len(lines)) + 1)
    return any(_is_nolint_for(lines[number - 1], rule) for number in numbers)


def _is_nolint_for(line: str, rule: str) -> bool:
    match = _NOLINT.search(line)
    if match is None:
        return False
    entries = (entry.split() for entry in match.group(1).split(","))
    return any(words[0] == rule for words in entries if words)
