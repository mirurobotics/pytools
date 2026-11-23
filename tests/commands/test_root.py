import pytest

from pytools.commands.root import run
from pytools.services.lint.lint import LintOptions
from pytools.services.lint.linter.rules import Config

_CONFIG = Config(
    max_func_len=30, max_file_len=300, max_nest_depth=2, exclude=frozenset()
)


def test_run_dispatches_to_lint(lint_calls: list[LintOptions]) -> None:
    run(["lint", "--paths", "src"])
    assert lint_calls == [LintOptions(paths=["src"], fix=True, linter_config=_CONFIG)]


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_run_rejects_missing_or_unknown_command(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(argv)
    assert excinfo.value.code == 2
