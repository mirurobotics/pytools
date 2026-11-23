import sys

import pytest

from pytools import __main__ as entry


def test_main_runs_command_line_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    argvs: list[list[str]] = []
    monkeypatch.setattr(entry, "run", argvs.append)
    monkeypatch.setattr(sys, "argv", ["pytools", "lint", "--no-fix"])
    entry.main()
    assert argvs == [["lint", "--no-fix"]]
