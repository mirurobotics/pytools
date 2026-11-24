from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.decl import DeclKind

type Parse = Callable[[str], CheckInput]

_KINDS: Final = """\
def run(): pass
def _helper(): pass
def __getattr__(name): pass
def _kept(): pass  # nolint: funcorder
class Runner:  # nolint: funcorder
    pass
"""
_OVERLOADS: Final = """\
@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x): return _convert(x)
def _convert(x): return x
"""
_PROPERTY: Final = """\
@property
def value(): return _load()
@value.setter
def value(new): _store(new)
def _load(): pass
def _store(new): pass
"""
_DECORATOR_PIN: Final = """\
def _deco(f): return f
@_deco
def run(): _deco(1)
"""
_CLASS_BODY_PIN: Final = """\
def _h(): pass
class T:
    X = _h()
    def run(self): return _h()
"""
_SETTER_CALLEE: Final = """\
def run(): return value
@property
def value(): return 1
@value.setter
def value(new): pass
"""
_TRANSITIVE_PIN: Final = """\
def _helper(): pass
def run(): _helper()
VALUE = run()
def other(): _helper()
"""
_FACTORY_PIN: Final = """\
def _helper(): pass
class Runner:
    def __init__(self): _helper()
def initialize(): return Runner()
VALUE = initialize()
def other(): _helper()
"""
_BARE_DECORATOR_PIN: Final = """\
def _setup(): pass
def _deco(f): _setup(); return f
@_deco
def run(): pass
def other(): _setup()
"""
_CALL_ARGUMENT_PIN: Final = """\
def _normalize(x): return x
def _key(x): return _normalize(x)
ORDERED = sorted(ITEMS, key=_key)
def run(x): return _normalize(x)
"""
_NESTED_DEF_PIN: Final = """\
def _helper(): pass
def initialize():
    def inner(): return _helper()
    return inner()
VALUE = initialize()
def other(): _helper()
"""
_METHOD_NAMED_LIKE_DECORATOR: Final = """\
def retry(f): return f
class Client:
    @retry
    def retry(self): pass
def _wrap(): return retry
"""
_MAIN_GUARD: Final = """\
def _helper(): pass
def main(): _helper()
if __name__ == "__main__":
    main()
"""
_NOLINT_METHOD: Final = """\
def _helper(): pass
class Runner:
    def run(self): _helper()  # nolint: funcorder
"""
_NOLINT_CLASS: Final = """\
def _helper(): pass
class Runner:  # nolint: funcorder
    def run(self): _helper()
"""
_NOLINT_GETTER: Final = """\
def run(): return value
@property
def value(): pass  # nolint: funcorder
@value.setter
def value(new): pass
"""
_NOLINT_OVERLOAD: Final = """\
def run(): return parse(1)
@overload
def parse(x: int) -> int: ...  # nolint: funcorder
def parse(x): return x
"""
_STUB_ANNOTATION: Final = """\
Json = dict
@overload
def parse(x: Json) -> Json: ...
def parse(x): return x
"""
_NEED_THROUGH_CALL: Final = """\
def _h(): pass
def _init(): return _h()
class T:
    x = _init()
"""
_VALUE_THROUGH_CALL: Final = """\
def _init(): return VALUE
VALUE = 1
class T:
    x = _init()
"""
_EXEMPT_CYCLE_MEMBER: Final = """\
def _e(): _a()  # nolint: funcorder
def run(): pass
def _a(): _b()
def _b(): _a(); _e()
def _c(): pass
"""


def test_build_gives_each_decl_a_kind(parse: Parse) -> None:
    kinds = {idx: decl.kind for idx, decl in _build(parse, _KINDS).decls.items()}
    assert kinds == {
        0: DeclKind.PUBLIC,
        1: DeclKind.PRIVATE,
        2: DeclKind.PUBLIC,
        3: DeclKind.EXEMPT,
        4: DeclKind.CLASS,
    }


@pytest.mark.parametrize(
    ("source", "stubs", "calls"),
    [
        pytest.param(_OVERLOADS, frozenset({0, 1}), {2: [3], 3: []}, id="overloads"),
        pytest.param(
            _PROPERTY, frozenset({0}), {1: [2, 3], 2: [], 3: []}, id="property"
        ),
    ],
)
def test_build_merges_a_def_with_its_stubs(
    parse: Parse, source: str, stubs: frozenset[int], calls: dict[int, list[int]]
) -> None:
    built = _build(parse, source)
    assert (built.stubs, built.calls) == (stubs, calls)


@pytest.mark.parametrize(
    ("source", "calls"),
    [
        pytest.param(_DECORATOR_PIN, {0: [], 1: []}, id="decorator"),
        pytest.param(
            "def _make(): pass\ndef run(x=_make()): return _make()\n",
            {0: [], 1: []},
            id="default",
        ),
        pytest.param(
            "def _t(): pass\ndef run(x: _t): return _t()\n",
            {0: [], 1: []},
            id="annotation",
        ),
        pytest.param(_CLASS_BODY_PIN, {0: [], 1: []}, id="class-body"),
        pytest.param(
            "def _h(): pass\nVALUE = _h()\ndef run(): return _h()\n",
            {0: [], 2: []},
            id="module-statement",
        ),
        pytest.param(
            "def _h(): pass\ndef run(): return _h()\n",
            {0: [], 1: [0]},
            id="no-import-time-use",
        ),
        pytest.param(_SETTER_CALLEE, {0: [2], 2: []}, id="own-setter-decorator"),
        pytest.param(_TRANSITIVE_PIN, {0: [], 1: [], 3: []}, id="transitive"),
        pytest.param(
            _FACTORY_PIN, {0: [], 1: [], 2: [], 4: []}, id="class-built-by-factory"
        ),
        pytest.param(
            _BARE_DECORATOR_PIN, {0: [], 1: [], 2: [], 3: []}, id="bare-decorator"
        ),
        pytest.param(_CALL_ARGUMENT_PIN, {0: [], 1: [], 3: []}, id="call-argument"),
        pytest.param(_NESTED_DEF_PIN, {0: [], 1: [], 3: []}, id="nested-def-called"),
        pytest.param(
            _METHOD_NAMED_LIKE_DECORATOR,
            {0: [], 1: [], 2: []},
            id="method-named-like-its-decorator",
        ),
    ],
)
def test_build_skips_calls_into_import_time_defs(
    parse: Parse, source: str, calls: dict[int, list[int]]
) -> None:
    assert _build(parse, source).calls == calls


@pytest.mark.parametrize(
    ("source", "calls"),
    [
        pytest.param(_MAIN_GUARD, {0: [], 1: [0]}, id="main-guard"),
        pytest.param(
            "def _h(): pass\ndef run(): _h()\nVALUE = run()\n",
            {0: [], 1: [0]},
            id="use-below-every-caller",
        ),
    ],
)
def test_build_enforces_calls_no_reorder_can_break(
    parse: Parse, source: str, calls: dict[int, list[int]]
) -> None:
    assert _build(parse, source).calls == calls


@pytest.mark.parametrize(
    ("source", "calls"),
    [
        pytest.param(
            "def _helper(): pass  # nolint: funcorder\ndef run(): _helper()\n",
            {0: [], 1: []},
            id="exempt-callee",
        ),
        pytest.param(
            "def _h(): pass\ndef run(): _h()  # nolint: funcorder\n",
            {0: [], 1: []},
            id="exempt-caller",
        ),
        pytest.param(_NOLINT_METHOD, {0: [], 1: [0]}, id="nolint-on-method"),
        pytest.param(_NOLINT_CLASS, {0: [], 1: [0]}, id="nolint-on-class"),
        pytest.param(_NOLINT_GETTER, {0: [], 2: []}, id="nolint-on-getter"),
        pytest.param(_NOLINT_OVERLOAD, {0: [], 2: []}, id="nolint-on-overload"),
    ],
)
def test_build_enforces_calls_unless_a_def_is_exempt(
    parse: Parse, source: str, calls: dict[int, list[int]]
) -> None:
    assert _build(parse, source).calls == calls


@pytest.mark.parametrize(
    ("source", "waiting"),
    [
        pytest.param(
            "def _b(): _a()\ndef run(): _a()\ndef _a(): _b()\n",
            frozenset({0}),
            id="cycle-called-from-outside",
        ),
        pytest.param(
            "def _b(): _a()\ndef _a(): _b()\ndef run(): pass\n",
            frozenset({1}),
            id="opener",
        ),
        pytest.param(_EXEMPT_CYCLE_MEMBER, frozenset({3}), id="exempt-member"),
    ],
)
def test_build_waits_cycle_members_for_a_cycle_caller(
    parse: Parse, source: str, waiting: frozenset[int]
) -> None:
    assert _build(parse, source).waiting == waiting


@pytest.mark.parametrize(
    ("source", "needs"),
    [
        pytest.param("C = 1\ndef run(x=C): pass\n", {1: frozenset({0})}, id="default"),
        pytest.param("def run(x=C): pass\nC = 1\n", {0: frozenset()}, id="below"),
        pytest.param("C = 1\ndef run(): return C\n", {1: frozenset()}, id="body"),
        pytest.param(_DECORATOR_PIN, {0: frozenset(), 1: frozenset({0})}, id="decl"),
        pytest.param(_STUB_ANNOTATION, {2: frozenset({0})}, id="stub-annotation"),
        pytest.param(
            _NEED_THROUGH_CALL,
            {0: frozenset(), 1: frozenset(), 2: frozenset({0, 1})},
            id="through-a-call",
        ),
        pytest.param(
            _VALUE_THROUGH_CALL,
            {0: frozenset(), 2: frozenset({0, 1})},
            id="value-through-a-call",
        ),
    ],
)
def test_build_finds_what_each_decl_uses_when_defined(
    parse: Parse, source: str, needs: dict[int, frozenset[int]]
) -> None:
    assert _build(parse, source).needs == needs


def _build(parse: Parse, source: str) -> model.Model:
    file = parse(source)
    return model.build(file, file.tree)
