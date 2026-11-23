import ast
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.analysis.comments import collect_comments


@pytest.fixture
def parse() -> Callable[[str], CheckInput]:
    """Parse source into a rule's input, as the linter does for each file."""

    def parse_source(source: str) -> CheckInput:
        tree = ast.parse(source)
        return CheckInput("a.py", tree, source.split("\n"), collect_comments(source))

    return parse_source
