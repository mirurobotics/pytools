import typing
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis import names
from pytools.services.lint.linter.analysis.analysis import CheckInput

Parse = Callable[[str], CheckInput]

_KINDS = """\
first = 1
class Second[Third]:
    fourth = 1
def fifth(sixth):
    seventh = 1
def test_eighth():
    pass
"""
_MULTILINE_EXCEPT = """\
try:
    pass
except (
    E
) as name:
    pass
"""
_SAME_LINE_EXCEPT = """\
try:
    pass
except (
    E
) as name: pass
"""
_MULTILINE_MATCH_AS = """\
match a:
    case (
        [1]
    ) as name:
        pass
"""
_MAPPING_REST = """\
match a:
    case {
        "k": 1,
        **name
    }:
        pass
"""


def test_scopes_match_the_nested_scope_type() -> None:
    nested = typing.get_args(names._Nested.__value__)
    assert set(names._scope_types()) == set(nested)


def test_declared_names_gives_each_kind_in_line_order(parse: Parse) -> None:
    found = [(name.text, name.kind) for name in names.declared_names(parse(_KINDS))]
    assert found == [
        ("first", names.NameKind.MODULE_VAR),
        ("Second", names.NameKind.CLASS),
        ("Third", names.NameKind.TYPE_PARAM),
        ("fourth", names.NameKind.CLASS_VAR),
        ("fifth", names.NameKind.FUNC),
        ("sixth", names.NameKind.LOCAL_VAR),
        ("seventh", names.NameKind.LOCAL_VAR),
        ("test_eighth", names.NameKind.TEST_FUNC),
    ]


@pytest.mark.parametrize(
    ("source", "line", "last_line"),
    [
        pytest.param("name = 1\n", 1, 1, id="binding"),
        pytest.param(_MULTILINE_EXCEPT, 5, 5, id="except-header-end"),
        pytest.param(_SAME_LINE_EXCEPT, 5, 5, id="except-same-line-body"),
        pytest.param(_MULTILINE_MATCH_AS, 4, 4, id="match-as-pattern-end"),
        pytest.param(_MAPPING_REST, 2, 5, id="mapping-rest-pattern"),
    ],
)
def test_declared_names_gives_lines(
    parse: Parse, source: str, line: int, last_line: int
) -> None:
    declared = names.declared_names(parse(source))
    assert [(name.line, name.last_line) for name in declared] == [(line, last_line)]
