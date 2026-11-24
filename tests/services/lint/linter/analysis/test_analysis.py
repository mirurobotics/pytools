import ast
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    function_body_lines,
    functions,
    is_code_line,
    line_groups,
    module_header_end,
    walk_outside,
)

type Parse = Callable[[str], CheckInput]

_FUNCTIONS = """\
class A:
    def method(self):
        def inner():
            pass


async def b():
    pass


def c():
    pass
"""
_WALK = """\
a = [b]
c = d
"""
_SOURCE = """\
a = 1

    # comment
b = 2  # trailing
c = '''
# not a comment
'''
# spaced \t
"""
_FUNCTION_BODIES = """\
def helper(
    first,
):
    return first
    # tail
# outside
class Point:
    async def fetch(self):
        def inner(): pass
        return inner
LIMIT = 1
"""
_MODULE_HEADER = """\
#!/usr/bin/env python3
# Copyright 2026 Example.

import os
"""


def test_diagnostic_str() -> None:
    diag = Diagnostic(path="src/a.py", line=42, message="function f is 31 lines")
    assert str(diag) == "src/a.py:42: function f is 31 lines"


def test_functions_lists_nested_and_async_by_line(parse: Parse) -> None:
    names = [func.name for func in functions(parse(_FUNCTIONS).tree)]
    assert names == ["method", "inner", "b", "c"]


def test_walk_outside_yields_depth_first(parse: Parse) -> None:
    nodes = walk_outside(parse(_WALK).tree.body, ())
    names = [node.id for node in nodes if isinstance(node, ast.Name)]
    assert names == ["a", "b", "c", "d"]


def test_walk_outside_does_not_enter_stop_nodes(parse: Parse) -> None:
    nodes = walk_outside(parse(_WALK).tree.body, (ast.List,))
    kinds = [type(node) for node in nodes if not isinstance(node, ast.expr_context)]
    assert kinds == [ast.Assign, ast.Name, ast.List, ast.Assign, ast.Name, ast.Name]


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        pytest.param(1, True, id="code"),
        pytest.param(2, False, id="blank"),
        pytest.param(3, False, id="comment-only"),
        pytest.param(4, True, id="trailing-comment"),
        pytest.param(6, True, id="hash-in-string"),
        pytest.param(8, False, id="comment-with-trailing-whitespace"),
    ],
)
def test_is_code_line(parse: Parse, number: int, expected: bool) -> None:
    assert is_code_line(parse(_SOURCE), number) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_FUNCTION_BODIES, {4, 5, 9, 10}, id="bodies"),
        pytest.param("def f(): pass\nLIMIT = 1\n", set(), id="one-line-def"),
        pytest.param(
            "def f(\n    first,\n): return first\nLIMIT = 1\n",
            set(),
            id="wrapped-one-line-def",
        ),
        pytest.param("LIMIT = 1\n", set(), id="no-functions"),
    ],
)
def test_function_body_lines(parse: Parse, source: str, expected: set[int]) -> None:
    assert function_body_lines(parse(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_MODULE_HEADER, 4, id="first-statement"),
        pytest.param("@cache\n\ndef f():\n    pass\n", 1, id="decorated"),
        pytest.param("", 1, id="empty"),
        pytest.param("# a note\n# another note\n", 3, id="comment-only"),
    ],
)
def test_module_header_end(parse: Parse, source: str, expected: int) -> None:
    assert module_header_end(parse(source)) == expected


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param([], [], id="empty"),
        pytest.param([3], [[3]], id="one-line"),
        pytest.param([1, 2, 4, 6, 7], [[1, 2], [4], [6, 7]], id="gaps"),
    ],
)
def test_line_groups(lines: list[int], expected: list[list[int]]) -> None:
    assert line_groups(lines) == expected
