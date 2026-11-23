import pytest

from pytools.commands.root import run
from pytools.services.lint.lint import LintOptions


def test_run_dispatches_to_lint(lint_calls: list[LintOptions]) -> None:
    run(["lint", "--paths", "src"])
    assert lint_calls == [LintOptions(paths=["src"], fix=True)]


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_run_rejects_missing_or_unknown_command(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(argv)
    assert excinfo.value.code == 2
