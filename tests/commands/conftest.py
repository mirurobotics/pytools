import pytest

from pytools.commands import lint
from pytools.services.lint.lint import LintOptions


@pytest.fixture
def lint_calls(monkeypatch: pytest.MonkeyPatch) -> list[LintOptions]:
    """Record the options each lint run receives instead of running linters."""
    calls: list[LintOptions] = []
    monkeypatch.setattr(lint, "run_lint", calls.append)
    return calls
