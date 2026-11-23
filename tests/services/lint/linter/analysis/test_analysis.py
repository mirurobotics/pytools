from pytools.services.lint.linter.analysis.analysis import Diagnostic


def test_diagnostic_str() -> None:
    diag = Diagnostic(path="src/a.py", line=42, message="function f is 31 lines")
    assert str(diag) == "src/a.py:42: function f is 31 lines"
