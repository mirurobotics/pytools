import typing

from pytools.services.lint.linter.analysis import names


def test_scopes_match_the_nested_scope_type() -> None:
    nested = typing.get_args(names._Nested.__value__)
    assert set(names._SCOPES) == set(nested)
