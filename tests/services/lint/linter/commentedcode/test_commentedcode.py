from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.commentedcode import commentedcode

type Parse = Callable[[str], CheckInput]

_FUNCTION_BODY: Final = """\
def helper():
    # first = 1
    # first += 1
    # return first
    return 2
"""
_TOP_LEVEL: Final = """\
# def old():
#     print("hi")

# LEGACY = 3
"""
_CODE_AFTER_PROSE: Final = """\
def helper():
    # the old way:
    #cleanup(True)
    pass
"""
_CONTROL_FLOW: Final = """\
# for item in items: pass

# while running: step()

# with lock: pass

# match value:
#     case 1:
#         pass

# try:
#     run()
# except OSError:
#     pass
"""
_INDENTED_RUNS: Final = """\
# def old():
#\tprint("hi")

#\tfirst = 1
#\treturn first

#first = 1
"""
_CALLS_AND_ASSIGNMENTS: Final = """\
# (run())

# await done

# point.x, items[0] = 1, 2

# prev = (
#     cur
# )

# yield value
"""
_METHOD_CHAIN: Final = """\
def helper():
    # (builder.
    #     run())
    pass
"""
_DEFINITIONS: Final = """\
# class Point: pass

# type Alias = Base

# import os

# from os import path

def helper():
    # counts: dict[str, int] = {}
    pass
"""
_BARE_ANNOTATIONS: Final = """\
# mu: Lock
#
# def lock():
#     mu.acquire()

# class Point:
#     first: int

def helper():
    # group: WaitGroup
    # group.add(1)
    pass
"""
_NESTED_BARE_ANNOTATION: Final = """\
def helper():
    # for item in items:
    #     buf: Buffer
    #     render(buf, item)
    pass
"""
_DOCSTRING: Final = """\
# def helper():
#     '''Do a thing.'''
"""
_EXAMPLE_UNDER_PROSE: Final = """\
# Example:
#     run()
#   value = run()
# fmt: off
"""
_NOLINT: Final = """\
# nolint: commentedcode
# first = 1

# nolint: funclen
# second = 2
"""
_MESSAGE: Final = "commented-out code; delete it instead"


def _diags(*lines: int) -> list[Diagnostic]:
    return [Diagnostic("a.py", line, _MESSAGE) for line in lines]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_FUNCTION_BODY, _diags(2), id="once-per-group"),
        pytest.param(_TOP_LEVEL, _diags(1, 4), id="top-level"),
        pytest.param(_CODE_AFTER_PROSE, _diags(3), id="code-line-after-prose"),
        pytest.param(_CONTROL_FLOW, _diags(1, 3, 5, 7, 11), id="control-flow"),
        pytest.param(_INDENTED_RUNS, _diags(1, 4, 7), id="indented-and-unspaced"),
        pytest.param(_CALLS_AND_ASSIGNMENTS, _diags(1, 3, 5, 7, 11), id="calls"),
        pytest.param(_METHOD_CHAIN, _diags(2), id="method-chain-across-lines"),
        pytest.param('# print("héllo", os.sep)\n', _diags(1), id="non-ascii-string"),
        pytest.param(_DEFINITIONS, _diags(1, 3, 5, 7, 10), id="definitions"),
        pytest.param(_BARE_ANNOTATIONS, _diags(1, 6, 10), id="bare-annotations"),
        pytest.param(_NESTED_BARE_ANNOTATION, _diags(2), id="nested-annotation"),
        pytest.param(_DOCSTRING, _diags(1), id="docstring"),
        pytest.param("#\n# first = 1\n", _diags(2), id="first-non-blank-line"),
        pytest.param("# noqa: E501\n# first = 1\n", _diags(2), id="after-directive"),
        pytest.param("import os\n# coding=utf-8\n", _diags(2), id="coding-after-code"),
        pytest.param("import os\n\n# coding=utf-8\n", _diags(3), id="coding-on-line-3"),
    ],
)
def test_check_reports_commented_out_code(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert commentedcode.check(parse(source)) == expected


@pytest.mark.parametrize(
    "comment",
    [
        "F returns the value of x.",
        "See https://example.com/docs for more.",
        "Note: call Init() first.",
        "TODO(ben): handle errors",
        "- list item",
        "a = b in this context, where f(x) = y.",
        "0 < len(p) < 10",
        "os.getcwd",
        "x.y",
        "Get(k) = v",
        "extension-method = token",
        "break",
        "{}",
        "{name}",
        "if ready: done",
        "v.(type)",
        "f()++",
        "e.g. Close()",
        "i.e. x.Run()",
        "cf. foo()",
        "# note",
        "def f(): e.g. run()",
        "获取用户信息(从缓存)",
        "状态=成功",
        "计数器++",
        "type assertion failed",
        "var name here",
        "const value",
        "def helper()",
        "type (or nil)",
        "var (see below)",
        "deprecated",
        "",
        "Note: text",
        "pass",
        "continue",
        "global state",
    ],
)
def test_check_skips_prose(parse: Parse, comment: str) -> None:
    assert commentedcode.check(parse(f"# {comment}\n")) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("# Note: text\n# Warning: more\n", id="bare-annotations-only"),
        pytest.param(_EXAMPLE_UNDER_PROSE, id="example-under-prose"),
        pytest.param("#\n#\n", id="blank-comments"),
        pytest.param("LIMIT = 20  # len(str(LIMIT))\n", id="trailing"),
        pytest.param('LABEL = "# first = 1"\n', id="hash-in-string"),
        pytest.param("# pylint: disable=too-many-lines\n", id="pylint-pragma"),
        pytest.param("# coding=utf-8\nimport os\n", id="encoding-declaration"),
        pytest.param("#!/usr/bin/env python\n# coding=utf-8\n", id="coding-on-line-2"),
        pytest.param("\n# coding=utf-8\n", id="coding-after-blank-line"),
    ],
)
def test_check_skips_groups_that_are_not_code(parse: Parse, source: str) -> None:
    assert commentedcode.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_NOLINT, _diags(5), id="first-line"),
        pytest.param("# run()\n# nolint: commentedcode\n# stop()\n", [], id="middle"),
        pytest.param("# first = 1\n# nolint: funclen, commentedcode\n", [], id="list"),
    ],
)
def test_check_honors_nolint(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert commentedcode.check(parse(source)) == expected


@pytest.mark.parametrize(
    "comment",
    [
        pytest.param("-" * 100_000 + "1", id="parser-stack"),
        pytest.param("a" + ".b" * 100_000, id="recursion-limit"),
    ],
)
def test_check_skips_comments_too_deep_to_parse(parse: Parse, comment: str) -> None:
    assert commentedcode.check(parse(f"# {comment}\n")) == []
