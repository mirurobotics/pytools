from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.fieldassert import fieldassert

type Parse = Callable[[str], CheckInput]

_THREE_FIELDS: Final = """\
def test_build():
    got = build()
    assert got.a == 1
    assert got.b == "b"
    assert got.a == 1
    assert got.c == [3]
"""
_TABLE_EXPECTED: Final = """\
def test_build(cases):
    for case in cases:
        got = build(case.given)
        assert got.a == case.want_a
        assert got.b == case.want_b
        assert got.c == case.want_c
        assert other == case.want_d
"""
_SWAPPED_HEADER: Final = """\
import os.path
from http import HTTPStatus

def test_build():
    got = build()
"""
_BLOCKS: Final = """\
def test_build(items, pair):
    first, second = build(), build()
    assert first.x == 1
    assert second.x == 2
    assert first.y == 3
    assert second.y == 4
    assert first.z == 5
    if first:
        assert second.z == 6
    match pair:
        case (left, _):
            assert items[0].a == 1
            assert items[0].b == 2
            assert (items[0]).c == 3
"""
_MODULE_AND_CLASS: Final = """\
got = build()
assert got.a == 1
assert got.b == 2
assert got.c == 3

class TestBuild:
    made = build()
    assert made.a == 1
    assert made.b == 2
    assert made.c == 3

    def test_fields(self):
        assert self.got.a == 1
        assert self.got.b == 2
        assert self.got.c == 3
"""
_OTHER_DEF_IMPORT: Final = """\
def unrelated():
    import sys as config

config = load()
assert config.a == 1
assert config.b == 2
assert config.c == 3
"""
_CALL_BASES: Final = """\
import http

def test_build():
    assert build().a == 1
    assert build().b == 2
    assert build().c == 3
    assert [make()][0].a == 1
    assert [make()][0].b == 2
    assert [make()][0].c == 3
    assert http.load().a == 1
    assert http.load().b == 2
    assert http.load().c == 3
"""
_BETWEEN: Final = """\
def test_build():
    got = build()
    assert got.meta.a == 1
    assert got.meta.b == 2
    {between}
    assert got.meta.c == 3
"""
_TWO_FIELDS: Final = """\
def test_build():
    got = build()
    assert got.a == 1
    assert got.b == 2
"""
_NOT_FIELDS: Final = """\
def test_request(case):
    code, body, err = do(case.request)
    assert code == case.want_code
    assert body == case.want_body
    assert err == case.want_err
    assert got.get_name() == case.want_name
    assert -code == case.want_kind
    assert [item.id] == case.want_ids
    assert {"x": item.id} == case.want_map
    assert (item.id,) == case.want_tuple
"""
_PACKAGE_FIELDS: Final = """\
from http import HTTPStatus

def test_status():
    assert HTTPStatus.OK == 200
    assert HTTPStatus.NOT_FOUND == 404
    assert HTTPStatus.INTERNAL_SERVER_ERROR == 500
"""
_NOT_EQUALITY: Final = """\
def test_build():
    got = build()
    assert "x" in got.a
    assert len(got.b) == 2
    assert got.c != 1
    assert got.d
    assert got.e == 1 == got.f
    assert got.g is None
"""
_REPEATED_FIELD: Final = """\
def test_count():
    counter = Counter()
    assert counter.count == 1
    assert counter.count == 1
    assert counter.count == 1
    assert counter.errors == 0
"""
_INDEX_CHANGE: Final = """\
def test_items():
    got, index = build(), 0
    assert got[index].a == 1
    index += 1
    assert got[index].b == 2
    index += 1
    assert got[index].c == 3
"""
_DEEP_SUM: Final = "got + " * 1999 + "got"
_DEEP_BASE: Final = f"""\
def test_build():
    assert ({_DEEP_SUM}).a == 1
    assert ({_DEEP_SUM}).b == 2
    assert ({_DEEP_SUM}).c == 3
"""
_HELPER: Final = """\
def check_thing(got):
    assert got.a == 1
    assert got.b == 2
    assert got.c == 3
"""
_RUN: Final = """\
def test_build():
    got = build()
    assert got.a == 1{first}
    assert got.b == 2
    assert got.c == 3{last}
"""


def _diag(line: int, count: int, base: str, root: str | None) -> Diagnostic:
    message = (
        f"{count} asserts compare fields of {base} one at a time; compare the whole"
        " value in one assert"
    )
    if root is not None:
        message += f", or move the checks into a helper that takes {root}"
    return Diagnostic("a.py", line, message)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_THREE_FIELDS, [_diag(3, 4, "got", "got")], id="three-fields"),
        pytest.param(
            _TABLE_EXPECTED, [_diag(4, 3, "got", "got")], id="grouped-by-actual"
        ),
        pytest.param(
            _BLOCKS,
            [
                _diag(3, 3, "first", "first"),
                _diag(12, 3, "items[0]", "items"),
            ],
            id="blocks",
        ),
        pytest.param(
            _MODULE_AND_CLASS,
            [
                _diag(2, 3, "got", "got"),
                _diag(8, 3, "made", "made"),
                _diag(13, 3, "self.got", "self"),
            ],
            id="module-and-class-bodies",
        ),
        pytest.param(
            _OTHER_DEF_IMPORT, [_diag(5, 3, "config", "config")], id="other-def-import"
        ),
        pytest.param(
            _CALL_BASES,
            [
                _diag(4, 3, "build()", None),
                _diag(7, 3, "[make()][0]", None),
                _diag(10, 3, "http.load()", None),
            ],
            id="call-bases",
        ),
    ],
)
def test_check_reports_field_runs(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert fieldassert.check(parse(source)) == expected


@pytest.mark.parametrize(
    "asserts",
    [
        pytest.param(("1 == got.a", "-2 == got.b", "3.5 == got.c"), id="numbers"),
        pytest.param(
            ("True == got.a", "False == got.b", "None == got.c"), id="singletons"
        ),
        pytest.param(
            ("[1] == got.a", '{"k": (1,)} == got.b', "{1} == got.c"), id="literals"
        ),
        pytest.param(
            (
                "HTTPStatus.OK == got.a",
                "os.path.sep == got.b",
                "-HTTPStatus.OK == got.c",
            ),
            id="package-constants",
        ),
    ],
)
def test_check_reports_swapped_args(parse: Parse, asserts: tuple[str, ...]) -> None:
    source = _SWAPPED_HEADER + "".join(f"    assert {line}\n" for line in asserts)
    assert fieldassert.check(parse(source)) == [_diag(6, 3, "got", "got")]


@pytest.mark.parametrize(
    ("between", "expected"),
    [
        pytest.param("_ = other.meta", [_diag(3, 3, "got.meta", "got")], id="other"),
        pytest.param("err = other()", [_diag(3, 3, "got.meta", "got")], id="unrelated"),
        pytest.param(
            "assert len(got.items) == max(1, int(got.size))",
            [_diag(3, 3, "got.meta", "got")],
            id="pure-builtins",
        ),
        pytest.param("got.stop()", [], id="method-call"),
        pytest.param("assert got.start()", [], id="call-in-assert"),
        pytest.param("assert other.x == got.reset()", [], id="call-in-field-assert"),
    ],
)
def test_check_splits_run_where_value_may_change(
    parse: Parse, between: str, expected: list[Diagnostic]
) -> None:
    source = _BETWEEN.format(between=between)
    assert fieldassert.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_TWO_FIELDS, id="two-fields"),
        pytest.param(_NOT_FIELDS, id="not-fields"),
        pytest.param(_PACKAGE_FIELDS, id="package-fields"),
        pytest.param(_NOT_EQUALITY, id="not-equality"),
        pytest.param(_REPEATED_FIELD, id="repeated-field"),
        pytest.param(_INDEX_CHANGE, id="index-change"),
        pytest.param(_HELPER, id="helper-param"),
        pytest.param(_DEEP_BASE, id="base-too-deep-to-unparse"),
    ],
)
def test_check_skips_code_that_is_not_a_field_run(parse: Parse, source: str) -> None:
    assert fieldassert.check(parse(source)) == []


@pytest.mark.parametrize(
    ("first", "last"),
    [
        pytest.param("  # nolint: fieldassert", "", id="first-line"),
        pytest.param("", "  # nolint: fieldassert", id="last-line"),
    ],
)
def test_check_skips_run_with_nolint(parse: Parse, first: str, last: str) -> None:
    source = _RUN.format(first=first, last=last)
    assert fieldassert.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param(
            _RUN.format(first="  # nolint: varname", last=""), 3, id="other-rule"
        ),
        pytest.param(
            "# nolint: fieldassert\n" + _RUN.format(first="", last=""),
            4,
            id="line-above",
        ),
    ],
)
def test_check_reports_run_without_its_nolint(
    parse: Parse, source: str, line: int
) -> None:
    assert fieldassert.check(parse(source)) == [_diag(line, 3, "got", "got")]
