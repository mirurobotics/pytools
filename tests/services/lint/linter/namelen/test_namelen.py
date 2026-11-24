from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.namelen import namelen

type Parse = Callable[[str], CheckInput]

_LOCAL_AT: Final = "a" * 20
_LOCAL_OVER: Final = "a" * 21
_NAME_AT: Final = "a" * 30
_NAME_OVER: Final = "a" * 31
_TEST_AT: Final = "test_" + "a" * 45
_TEST_OVER: Final = "test_" + "a" * 46
_LONG: Final = "x" * 31

_REBOUND: Final = """\
def f():
    {0} = 1
    {0} = 2
"""
_NESTED: Final = """\
def outer():
    def inner():
        {0} = 1

    {0} = 2
"""
_COMPREHENSION: Final = """\
def f():
    {0} = 1
    return [{0} for {0} in a]
"""
_LAMBDA: Final = """\
def f():
    {0} = 1
    return lambda {0}: {0}
"""
_COMPREHENSION_WALRUS: Final = """\
def f():
    a = [({0} := b) for b in c]
    {0} = 1
"""
_TYPE_PARAMETERS: Final = """\
{0} = 1
type A[{0}] = int
type B[{0}] = int
def f[{0}]():
    global {0}
"""
_NOLINT_ON_PARAMETER: Final = """\
def f(
    {},  # nolint: namelen
):
    pass
"""
_NOLINT_ON_FIRST_IN_DICT: Final = """\
def f():
    return {{
        "a": ({0} := 1),  # nolint: namelen
        ({0} := 2): 3,
    }}
"""
_NOLINT_ON_MAPPING_REST: Final = """\
def f():
    match a:
        case {{
            "k": 1,
            **{}  # nolint: namelen
        }}:
            pass
"""
_NOLINT_ON_EXCEPT_ALIAS: Final = """\
def f():
    try:
        pass
    except (
        E
    ) as {}:  # nolint: namelen
        pass
"""
_NOLINT_IN_EXCEPT_BODY: Final = """\
try:
    pass
except E as {}:
    # nolint: namelen
    pass
"""
_MULTILINE_MATCH_AS: Final = """\
def f():
    match a:
        case (
            [b]
        ) as {}:
            pass
"""
_MULTILINE_EXCEPT: Final = """\
def f():
    try:
        pass
    except (
        E,
    ) as {}:
        pass
"""


def _diag(line: int, name: str, limit: int) -> Diagnostic:
    message = f'name "{name}" is {len(name)} chars (limit {limit})'
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(f"def f():\n    {_LOCAL_AT} = 1\n", [], id="local-at"),
        pytest.param(
            f"def f():\n    {_LOCAL_OVER} = 1\n",
            [_diag(2, _LOCAL_OVER, 20)],
            id="local-over",
        ),
        pytest.param(f"{_NAME_AT} = 1\n", [], id="module-at"),
        pytest.param(
            f"{_NAME_OVER} = 1\n", [_diag(1, _NAME_OVER, 30)], id="module-over"
        ),
        pytest.param(f"def {_TEST_AT}():\n    pass\n", [], id="test-at"),
        pytest.param(
            f"def {_TEST_OVER}():\n    pass\n",
            [_diag(1, _TEST_OVER, 50)],
            id="test-over",
        ),
    ],
)
def test_check_reports_names_over_their_limit(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert namelen.check(parse(source)) == expected


def test_check_reports_first_binding_in_a_scope(parse: Parse) -> None:
    source = _REBOUND.format(_LOCAL_OVER)
    assert namelen.check(parse(source)) == [_diag(2, _LOCAL_OVER, 20)]


@pytest.mark.parametrize(
    ("template", "lines"),
    [
        pytest.param(_NESTED, [3, 5], id="nested-function"),
        pytest.param(_COMPREHENSION, [2, 3], id="comprehension"),
        pytest.param(_LAMBDA, [2, 3], id="lambda"),
        pytest.param(_COMPREHENSION_WALRUS, [2], id="comprehension-walrus"),
        pytest.param(_TYPE_PARAMETERS, [2, 3, 4], id="type-parameters"),
    ],
)
def test_check_reports_a_name_once_per_scope(
    parse: Parse, template: str, lines: list[int]
) -> None:
    expected = [_diag(line, _LOCAL_OVER, 20) for line in lines]
    assert namelen.check(parse(template.format(_LOCAL_OVER))) == expected


@pytest.mark.parametrize(
    ("template", "line", "limit"),
    [
        pytest.param("def f():\n    {} = 1\n", 2, 20, id="assign"),
        pytest.param("def f():\n    {}: int = 1\n", 2, 20, id="annotated"),
        pytest.param("def f():\n    {} += 1\n", 2, 20, id="augmented"),
        pytest.param("def f():\n    a, *{} = b\n", 2, 20, id="unpacking"),
        pytest.param(
            "def f():\n    if ({} := g()):\n        pass\n", 2, 20, id="walrus"
        ),
        pytest.param("def f():\n    for {} in a:\n        pass\n", 2, 20, id="for"),
        pytest.param("def f():\n    with a as {}:\n        pass\n", 2, 20, id="with"),
        pytest.param(
            "def f():\n    try:\n        pass\n    except E as {}:\n        pass\n",
            4,
            20,
            id="except",
        ),
        pytest.param(_MULTILINE_EXCEPT, 6, 20, id="multiline-except"),
        pytest.param(_MULTILINE_MATCH_AS, 5, 20, id="multiline-match-as"),
        pytest.param(
            "def f():\n    match a:\n        case [{}]:\n            pass\n",
            3,
            20,
            id="match-capture",
        ),
        pytest.param(
            "def f():\n    match a:\n        case [*{}]:\n            pass\n",
            3,
            20,
            id="match-star",
        ),
        pytest.param(
            "def f():\n    match a:\n        case {{**{}}}:\n            pass\n",
            3,
            20,
            id="match-mapping-rest",
        ),
        pytest.param("def f({}):\n    pass\n", 1, 20, id="parameter"),
        pytest.param("def f(*{}):\n    pass\n", 1, 20, id="var-positional"),
        pytest.param("def f(**{}):\n    pass\n", 1, 20, id="var-keyword"),
        pytest.param("f = lambda {}: 1\n", 1, 20, id="lambda-parameter"),
        pytest.param("a = [1 for {} in b]\n", 1, 20, id="comprehension-target"),
        pytest.param("def f[{}]():\n    pass\n", 1, 20, id="type-parameter"),
        pytest.param("def f[**{}]():\n    pass\n", 1, 20, id="param-spec"),
        pytest.param("def f[*{}]():\n    pass\n", 1, 20, id="type-var-tuple"),
        pytest.param("class A[{}]:\n    pass\n", 1, 20, id="class-type-parameter"),
        pytest.param("type A[{}] = int\n", 1, 20, id="alias-type-parameter"),
        pytest.param("def {}():\n    pass\n", 1, 30, id="function"),
        pytest.param("async def {}():\n    pass\n", 1, 30, id="async-function"),
        pytest.param("def f():\n    def {}():\n        pass\n", 2, 30, id="inner-def"),
        pytest.param("class {}:\n    pass\n", 1, 30, id="class"),
        pytest.param("{} = 1\n", 1, 30, id="module-name"),
        pytest.param("class A:\n    {} = 1\n", 2, 30, id="class-name"),
    ],
)
def test_check_reports_each_binding_kind(
    parse: Parse, template: str, line: int, limit: int
) -> None:
    diags = namelen.check(parse(template.format(_LONG)))
    assert diags == [_diag(line, _LONG, limit)]


@pytest.mark.parametrize(
    "template",
    [
        pytest.param("def f(a=({} := 1)):\n    pass\n", id="default"),
        pytest.param("def f(a: ({} := int)):\n    pass\n", id="annotation"),
        pytest.param("def f() -> ({} := int):\n    pass\n", id="return-annotation"),
        pytest.param("f = lambda a=({} := 1): a\n", id="lambda-default"),
        pytest.param("@({} := d)\ndef f():\n    pass\n", id="decorator"),
        pytest.param("class A(({} := B)):\n    pass\n", id="class-base"),
        pytest.param("a = [({} := b) for b in c]\n", id="comprehension"),
    ],
)
def test_check_binds_walrus_in_the_outer_scope(parse: Parse, template: str) -> None:
    diags = namelen.check(parse(template.format(_LONG)))
    assert diags == [_diag(1, _LONG, 30)]


@pytest.mark.parametrize(
    "template",
    [
        pytest.param("import {}\n", id="import"),
        pytest.param("import a as {}\n", id="import-as"),
        pytest.param("from a import {}\n", id="from-import"),
        pytest.param("def f():\n    global {}\n", id="global"),
        pytest.param("def f():\n    def g():\n        nonlocal {}\n", id="nonlocal"),
        pytest.param("def f():\n    global {0}\n    {0} = 1\n", id="global-assigned"),
        pytest.param(
            "def f():\n    def g():\n        nonlocal {0}\n        {0} = 1\n",
            id="nonlocal-assigned",
        ),
        pytest.param("def f(a):\n    a.{} = 1\n", id="attribute-target"),
        pytest.param("def f():\n    return {}\n", id="read"),
    ],
)
def test_check_ignores_names_it_does_not_bind(parse: Parse, template: str) -> None:
    assert namelen.check(parse(template.format(_LONG))) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(f"{_LONG} = 1  # nolint: namelen\n", id="binding-line"),
        pytest.param(
            f"@decorator\ndef {_LONG}():  # nolint: namelen\n    pass\n",
            id="def-line",
        ),
        pytest.param(
            f"@decorator  # nolint: namelen\ndef {_LONG}():\n    pass\n",
            id="decorator-line",
        ),
        pytest.param(
            f"# nolint: namelen\nclass {_LONG}:\n    pass\n", id="line-above-class"
        ),
        pytest.param(_NOLINT_ON_PARAMETER.format(_LONG), id="parameter-line"),
        pytest.param(_NOLINT_ON_MAPPING_REST.format(_LONG), id="mapping-rest-line"),
        pytest.param(_NOLINT_ON_EXCEPT_ALIAS.format(_LONG), id="except-alias-line"),
        pytest.param(
            _NOLINT_ON_FIRST_IN_DICT.format(_LONG), id="first-binding-in-dict"
        ),
    ],
)
def test_check_skips_name_with_nolint(parse: Parse, source: str) -> None:
    assert namelen.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param(f"{_LONG} = 1  # nolint: other\n", 1, id="other-rule"),
        pytest.param(f"# nolint: namelen\n{_LONG} = 1\n", 2, id="line-above"),
        pytest.param(
            f"{_LONG} = 1\n{_LONG} = 2  # nolint: namelen\n", 1, id="later-binding"
        ),
        pytest.param(_NOLINT_IN_EXCEPT_BODY.format(_LONG), 3, id="except-body"),
    ],
)
def test_check_reports_name_without_its_nolint(
    parse: Parse, source: str, line: int
) -> None:
    assert namelen.check(parse(source)) == [_diag(line, _LONG, 30)]
