import ast
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import render

type Parse = Callable[[str], CheckInput]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("a = 1\nb = 2\n", False, id="own-lines"),
        pytest.param("a = 1; b = 2\n", True, id="semicolon"),
        pytest.param("def f(): pass\nb = 2\n", False, id="def-on-one-line"),
    ],
)
def test_has_shared_lines_in_module(parse: Parse, source: str, expected: bool) -> None:
    file = parse(source)
    assert render.has_shared_lines(file, file.tree) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("class T:\n    a = 1\n", False, id="own-lines"),
        pytest.param("class T: a = 1\n", True, id="header-line"),
        pytest.param("class T(\n    Base,\n):\n    a = 1\n", False, id="long-header"),
    ],
)
def test_has_shared_lines_in_class(parse: Parse, source: str, expected: bool) -> None:
    file = parse(source)
    assert render.has_shared_lines(file, _class_at(file, 0)) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("a = 1\nb = 2\n", "b = 2\na = 1\n", id="swap"),
        pytest.param(
            "# about a\na = 1\nb = 2\n",
            "b = 2\n# about a\na = 1\n",
            id="attached-comment-moves",
        ),
        pytest.param(
            "# header\n\na = 1\nb = 2\n",
            "# header\n\nb = 2\na = 1\n",
            id="detached-header-stays",
        ),
        pytest.param(
            "a = 1\n# about b\n\nb = 2\nc = 3\n",
            "# about b\n\nb = 2\na = 1\nc = 3\n",
            id="gap-moves",
        ),
    ],
)
def test_render_lays_out_module(parse: Parse, source: str, expected: str) -> None:
    file = parse(source)
    order = [1, 0, *range(2, len(file.tree.body))]
    assert render.render(file, {file.tree: order}) == expected


def test_render_lays_out_nested_scope_in_moved_chunk(parse: Parse) -> None:
    file = parse("a = 1\nclass T:\n    x = 1\n    y = 2\nb = 2\n")
    orders: dict[ast.Module | ast.ClassDef, list[int]] = {
        file.tree: [1, 0, 2],
        _class_at(file, 1): [1, 0],
    }
    expected = "class T:\n    y = 2\n    x = 1\na = 1\nb = 2\n"
    assert render.render(file, orders) == expected


def _class_at(file: CheckInput, idx: int) -> ast.ClassDef:
    found = file.tree.body[idx]
    assert isinstance(found, ast.ClassDef)
    return found
