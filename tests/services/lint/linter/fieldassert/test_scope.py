import ast
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, functions
from pytools.services.lint.linter.fieldassert.scope import (
    Bindings,
    changed_names,
    import_names,
    new_scope,
    root_name,
)

type Parse = Callable[[str], CheckInput]


@pytest.mark.parametrize(
    ("source", "name"),
    [
        pytest.param("def check(got): pass\n", "got", id="helper"),
        pytest.param(
            "def check(got):\n    def run(): pass\n", "got", id="closure-in-helper"
        ),
        pytest.param("class T:\n    def check(self): pass\n", "self", id="method"),
    ],
)
def test_is_helper_param_accepts_helper_param(
    parse: Parse, source: str, name: str
) -> None:
    assert _bindings(parse, source).is_helper_param(name)


@pytest.mark.parametrize(
    ("source", "name"),
    [
        pytest.param("def test_build(got): pass\n", "got", id="test-fixture"),
        pytest.param("def check():\n    got = build()\n", "got", id="local"),
        pytest.param(
            "def check(got):\n    def run():\n        got = build()\n",
            "got",
            id="shadowed",
        ),
        pytest.param("got = build()\n", "got", id="module"),
        pytest.param("def check(got): pass\n", None, id="no-root"),
    ],
)
def test_is_helper_param_rejects_other_names(
    parse: Parse, source: str, name: str | None
) -> None:
    assert not _bindings(parse, source).is_helper_param(name)


@pytest.mark.parametrize(
    ("source", "expr"),
    [
        pytest.param("import http\n", "http.HTTPStatus", id="module"),
        pytest.param("import os.path\n", "os.path.sep", id="dotted-import"),
        pytest.param("from http import HTTPStatus\n", "HTTPStatus", id="from-import"),
        pytest.param("import app.config as cfg\n", "cfg.debug", id="import-alias"),
        pytest.param("def run():\n    import json\n", "json", id="local-import"),
    ],
)
def test_is_pkg_accepts_imported_paths(parse: Parse, source: str, expr: str) -> None:
    assert _bindings(parse, source).is_pkg(_expr(expr))


@pytest.mark.parametrize(
    ("source", "expr"),
    [
        pytest.param("import app.config as cfg\n", "config.debug", id="aliased-path"),
        pytest.param(
            "import http\ndef run():\n    http = build()\n",
            "http.HTTPStatus",
            id="shadowed-import",
        ),
        pytest.param("import http\n", "http.load().value", id="call-base"),
        pytest.param("", "got.value", id="not-imported"),
    ],
)
def test_is_pkg_rejects_other_values(parse: Parse, source: str, expr: str) -> None:
    assert not _bindings(parse, source).is_pkg(_expr(expr))


@pytest.mark.parametrize(
    ("stmt", "expected"),
    [
        pytest.param("got.stop()", {"got"}, id="method-call"),
        pytest.param("fill(got)", {"fill", "got"}, id="call-argument"),
        pytest.param("for got in items:\n    pass", {"got", "items"}, id="loop"),
        pytest.param("got = build()", {"got", "build"}, id="reassign"),
        pytest.param("got.count += 1", {"got"}, id="augmented"),
        pytest.param("got.count, other = 1, 2", {"got", "other"}, id="unpacking"),
        pytest.param(
            "if ready:\n    got = build()", {"ready", "got", "build"}, id="nested"
        ),
        pytest.param("_ = other.meta", {"_", "other"}, id="attribute-not-a-name"),
        pytest.param(
            "def run():\n    got = other()", {"got", "other"}, id="nested-def"
        ),
        pytest.param("assert got.start()", {"got"}, id="assert-method-call"),
        pytest.param("assert mutate(got)", {"mutate", "got"}, id="assert-call"),
        pytest.param("assert sorted(got.items)", {"sorted", "got"}, id="assert-sorted"),
        pytest.param("assert other == (lambda: got.ok)", {"got"}, id="assert-lambda"),
        pytest.param(
            "assert (count := got.count) > 0", {"count", "got"}, id="assert-walrus"
        ),
        pytest.param(
            "assert len(got.items) == max(min(got.low), int(got.size), str(got.id))",
            set(),
            id="assert-pure-builtins",
        ),
        pytest.param("assert -got.count < other", set(), id="assert-read-only"),
    ],
)
def test_changed_names_returns_names_stmt_may_change(
    stmt: str, expected: set[str]
) -> None:
    assert changed_names(ast.parse(stmt).body[0]) == frozenset(expected)


@pytest.mark.parametrize(
    ("source", "expr", "expected"),
    [
        pytest.param("", "got", "got", id="name"),
        pytest.param("", "got.meta", "got", id="attribute"),
        pytest.param("", "got[index]", "got", id="subscript"),
        pytest.param("", "got.meta()", "got", id="method-call"),
        pytest.param("", "build()", None, id="call"),
        pytest.param("import http\n", "http.load()", None, id="package-call"),
        pytest.param("", "[make()][0]", None, id="literal"),
        pytest.param("", "(first or second).meta", None, id="expression"),
    ],
)
def test_root_name_returns_variable_expr_reads(
    parse: Parse, source: str, expr: str, expected: str | None
) -> None:
    assert root_name(_expr(expr), _bindings(parse, source)) == expected


def _bindings(parse: Parse, source: str) -> Bindings:
    file = parse(source)
    scopes = tuple(new_scope(file, func) for func in functions(file.tree))
    return Bindings(scopes, import_names(file.tree))


def _expr(text: str) -> ast.expr:
    return ast.parse(text, mode="eval").body
