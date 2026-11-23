from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.varname import varname

Parse = Callable[[str], CheckInput]

_REBOUND = """\
def f():
    n = 1
    n = 2
"""
_MULTILINE_EXCEPT = """\
def f():
    try:
        pass
    except (
        E,
    ) as n:
        pass
"""
_NOLINT_ON_PARAMETER = """\
def f(
    n,  # nolint: varname
):
    pass
"""
_NOLINT_ON_EXCEPT_ALIAS = """\
def f():
    try:
        pass
    except (
        E
    ) as n:  # nolint: varname
        pass
"""
_NOLINT_ON_MAPPING_REST = """\
def f():
    match a:
        case {
            "k": 1,
            **n  # nolint: varname
        }:
            pass
"""
_NOLINT_IN_EXCEPT_BODY = """\
try:
    pass
except E as n:
    # nolint: varname
    pass
"""


def _diag(line: int, name: str) -> Diagnostic:
    message = f'variable name "{name}" is shorter than 3 chars; use a descriptive name'
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("def f():\n    n = 1\n", [_diag(2, "n")], id="one-char"),
        pytest.param("def f():\n    dx = 1\n", [_diag(2, "dx")], id="two-chars"),
        pytest.param("def f():\n    num = 1\n", [], id="three-chars"),
        pytest.param("n = 1\n", [_diag(1, "n")], id="module-variable"),
    ],
)
def test_check_reports_names_under_three_chars(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert varname.check(parse(source)) == expected


@pytest.mark.parametrize("name", ["_", "i", "a", "b", "ok", "id", "db"])
def test_check_allows_listed_names(parse: Parse, name: str) -> None:
    assert varname.check(parse(f"{name} = 1\ndef f({name}):\n    pass\n")) == []


def test_check_reports_first_binding_in_a_scope(parse: Parse) -> None:
    assert varname.check(parse(_REBOUND)) == [_diag(2, "n")]


@pytest.mark.parametrize(
    ("template", "line"),
    [
        pytest.param("def f():\n    {}: int = 1\n", 2, id="annotated"),
        pytest.param("def f():\n    {} += 1\n", 2, id="augmented"),
        pytest.param("def f():\n    a, *{} = b\n", 2, id="unpacking"),
        pytest.param("def f():\n    if ({} := g()):\n        pass\n", 2, id="walrus"),
        pytest.param("def f():\n    for {} in a:\n        pass\n", 2, id="for"),
        pytest.param("def f():\n    with a as {}:\n        pass\n", 2, id="with"),
        pytest.param(
            "def f():\n    try:\n        pass\n    except E as {}:\n        pass\n",
            4,
            id="except",
        ),
        pytest.param(_MULTILINE_EXCEPT, 6, id="multiline-except"),
        pytest.param(
            "def f():\n    match a:\n        case [{}]:\n            pass\n",
            3,
            id="match-capture",
        ),
        pytest.param(
            "def f():\n    match a:\n        case [*{}]:\n            pass\n",
            3,
            id="match-star",
        ),
        pytest.param(
            "def f():\n    match a:\n        case {{**{}}}:\n            pass\n",
            3,
            id="match-mapping-rest",
        ),
        pytest.param("def f({}):\n    pass\n", 1, id="parameter"),
        pytest.param("def f(*{}):\n    pass\n", 1, id="var-positional"),
        pytest.param("def f(**{}):\n    pass\n", 1, id="var-keyword"),
        pytest.param("a = lambda {}: 1\n", 1, id="lambda-parameter"),
        pytest.param("a = [1 for {} in b]\n", 1, id="comprehension-target"),
        pytest.param("a = [({} := b) for b in c]\n", 1, id="comprehension-walrus"),
    ],
)
def test_check_reports_each_variable_kind(
    parse: Parse, template: str, line: int
) -> None:
    assert varname.check(parse(template.format("n"))) == [_diag(line, "n")]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("class A:\n    n = 1\n", id="class-level"),
        pytest.param("def fn[T]():\n    pass\n", id="type-parameter"),
        pytest.param("def fn[**P]():\n    pass\n", id="param-spec"),
        pytest.param("def fn[*T]():\n    pass\n", id="type-var-tuple"),
        pytest.param("class A[T]:\n    pass\n", id="class-type-parameter"),
        pytest.param("type Alias[T] = int\n", id="alias-type-parameter"),
        pytest.param("def fn():\n    pass\n", id="function"),
        pytest.param("async def fn():\n    pass\n", id="async-function"),
        pytest.param("class A:\n    pass\n", id="class"),
    ],
)
def test_check_skips_names_that_are_not_variables(parse: Parse, source: str) -> None:
    assert varname.check(parse(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("n = 1  # nolint: varname\n", id="binding-line"),
        pytest.param(_NOLINT_ON_PARAMETER, id="parameter-line"),
        pytest.param(_NOLINT_ON_EXCEPT_ALIAS, id="except-alias-line"),
        pytest.param(_NOLINT_ON_MAPPING_REST, id="mapping-rest-line"),
    ],
)
def test_check_skips_name_with_nolint(parse: Parse, source: str) -> None:
    assert varname.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param("n = 1  # nolint: namelen\n", 1, id="other-rule"),
        pytest.param("# nolint: varname\nn = 1\n", 2, id="line-above"),
        pytest.param("n = 1\nn = 2  # nolint: varname\n", 1, id="later-binding"),
        pytest.param(_NOLINT_IN_EXCEPT_BODY, 3, id="except-body"),
    ],
)
def test_check_reports_name_without_its_nolint(
    parse: Parse, source: str, line: int
) -> None:
    assert varname.check(parse(source)) == [_diag(line, "n")]
