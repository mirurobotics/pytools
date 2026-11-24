import ast
from collections.abc import Callable

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Function
from pytools.services.lint.linter.funcorder.inert import is_inert

type Parse = Callable[[str], CheckInput]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("def f(x: int | None = 1) -> list[int]: pass\n", id="typed-def"),
        pytest.param("def f(x: a.B[int], y: 'T') -> None: pass\n", id="dotted-hint"),
        pytest.param("@dataclass\nclass P:\n    x: tuple[int, ...]\n", id="dataclass"),
        pytest.param("@dataclasses.dataclass(eq=True)\nclass P: pass\n", id="module"),
        pytest.param("@functools.lru_cache(maxsize=None)\ndef f(): pass\n", id="call"),
        pytest.param("@wraps(func)\ndef f(): pass\n", id="name-argument"),
        pytest.param(
            "class P:\n    'doc'\n    x = 1\n    def f(self): pass\n", id="class"
        ),
    ],
)
def test_is_inert_accepts_definition_running_no_code(parse: Parse, source: str) -> None:
    assert is_inert(_decl(parse, source))


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("@register\ndef f(): pass\n", id="unknown-decorator"),
        pytest.param("@x.dataclass\nclass P: pass\n", id="unknown-module"),
        pytest.param("@dataclass(eq=1 + 1)\nclass P: pass\n", id="computed-argument"),
        pytest.param("@(d := deco)\ndef f(): pass\n", id="walrus-decorator"),
        pytest.param("def f(x: g()): pass\n", id="call-annotation"),
        pytest.param("def f(x: (y := int)): pass\n", id="walrus-annotation"),
        pytest.param("def f() -> [i for i in t]: pass\n", id="comprehension"),
        pytest.param("def f(x: lambda: 1): pass\n", id="lambda-annotation"),
        pytest.param("def f(x=g()): pass\n", id="call-default"),
        pytest.param("class P(Base): pass\n", id="base"),
        pytest.param("class P(metaclass=1): pass\n", id="keyword"),
        pytest.param("class P:\n    x: int = f()\n", id="annotated-value"),
        pytest.param("class P:\n    x: f() = 1\n", id="class-annotation"),
        pytest.param("class P:\n    a.b = 1\n", id="attribute-target"),
        pytest.param("class P:\n    print()\n", id="call-in-body"),
        pytest.param("class P:\n    @register\n    def f(self): pass\n", id="method"),
    ],
)
def test_is_inert_rejects_definition_running_code(parse: Parse, source: str) -> None:
    assert not is_inert(_decl(parse, source))


def _decl(parse: Parse, source: str) -> Function | ast.ClassDef:
    stmt = parse(source).tree.body[0]
    assert isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    return stmt
