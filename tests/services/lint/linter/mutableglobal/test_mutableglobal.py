from collections.abc import Callable
from typing import Final

import pytest

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic
from pytools.services.lint.linter.mutableglobal import mutableglobal

type Parse = Callable[[str], CheckInput]

_COMPOUND: Final = """\
if a:
    first = 1
else:
    second = 2
try:
    third = 1
except E:
    fourth = None
for fifth in a:
    pass
with a as sixth:
    pass
"""
_NOT_MODULE_LEVEL: Final = """\
class Point:
    origin = 0

def handler(event):
    count = 1
    return [item for item in event]
"""
_REBOUND_DEFS: Final = """\
def handler():
    pass

handler = wrap(handler)

class Point:
    pass

Point = dataclass(Point)
"""
_GLOBAL_WRITE: Final = """\
LIMIT: Final = 1

def reset():
    global LIMIT
    LIMIT = 2
"""
_FORMAT_SPEC: Final = """\
WIDTH: Final = 3
LABEL: Final = f"{WIDTH!r:>{WIDTH}}-{WIDTH}"
"""
_MULTILINE_NOLINT: Final = """\
# nolint: mutableglobal
__all__ = [
    "run",
]
"""
_LONG_CHAIN: Final = "LINE: Final = " + '"a" + ' * 2000 + '"a"\n'
_MESSAGE: Final = (
    "mutable global variable: use a Final constant, a type statement"
    " or a function instead"
)


def _diags(*lines: int) -> list[Diagnostic]:
    return [Diagnostic("a.py", line, _MESSAGE) for line in lines]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("counter = 0\n", _diags(1), id="assignment"),
        pytest.param("counter: int = 0\n", _diags(1), id="annotated"),
        pytest.param("counter: int\n", _diags(1), id="annotated-without-value"),
        pytest.param("counter += 1\n", _diags(1), id="augmented"),
        pytest.param("(counter := 1)\n", _diags(1), id="walrus"),
        pytest.param("first, second = 1, 2\n", _diags(1, 1), id="unpacking"),
        pytest.param("counter = 0\ncounter = 1\n", _diags(1), id="rebound"),
        pytest.param("cache = {}\n", _diags(1), id="dict"),
        pytest.param('pattern = re.compile("a")\n', _diags(1), id="compiled-regex"),
        pytest.param("lock = threading.Lock()\n", _diags(1), id="lock"),
        pytest.param("stdout = sys.stdout\n", _diags(1), id="dotted-reference"),
        pytest.param('missing = LookupError("x")\n', _diags(1), id="exception"),
        pytest.param("_ = setup()\n", _diags(1), id="underscore"),
        pytest.param('__all__ = ["run"]\n', _diags(1), id="dunder-all"),
        pytest.param("Alias: TypeAlias = int\n", _diags(1), id="type-alias-annotation"),
        pytest.param(_COMPOUND, _diags(2, 4, 6, 8, 9, 11), id="compound-statements"),
    ],
)
def test_check_reports_module_variables(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert mutableglobal.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("type Alias = int\n", id="type-statement"),
        pytest.param("def handler():\n    pass\n", id="function"),
        pytest.param("class Point:\n    pass\n", id="class"),
        pytest.param("class NotFoundError(LookupError):\n    pass\n", id="error"),
        pytest.param(_NOT_MODULE_LEVEL, id="class-and-local-variables"),
        pytest.param(_REBOUND_DEFS, id="rebound-def-and-class"),
        pytest.param(_GLOBAL_WRITE, id="global-write"),
    ],
)
def test_check_skips_names_that_are_not_variables(parse: Parse, source: str) -> None:
    assert mutableglobal.check(parse(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("LIMIT: Final = 3\n", id="literal"),
        pytest.param("LIMIT: Final[int] = 3\n", id="subscripted-final"),
        pytest.param("LIMIT: typing.Final = 3\n", id="qualified-final"),
        pytest.param("LIMIT: Final = -1\n", id="unary-operator"),
        pytest.param('LINE: Final = "-" * 3\n', id="binary-operator"),
        pytest.param("DEBUG: Final = False or True\n", id="bool-operator"),
        pytest.param('WINDOWS: Final = sys.platform == "win32"\n', id="comparison"),
        pytest.param('NAME: Final = "a" if DEBUG else "b"\n', id="conditional"),
        pytest.param("MAX: Final = LIMIT + 1\n", id="name"),
        pytest.param("from re import I\nFLAGS: Final = I\n", id="imported-name"),
        pytest.param("FLAGS: Final = re.I | re.M\n", id="dotted-reference"),
        pytest.param("SEP: Final = os.path.sep\n", id="nested-dotted-reference"),
        pytest.param("KINDS: Final = (ast.Name, (1, ast.Call))\n", id="tuple"),
        pytest.param("NONE: Final = frozenset()\n", id="empty-frozenset"),
        pytest.param('KEYS: Final = frozenset({"a", ast.Name})\n', id="frozenset-set"),
        pytest.param('KEYS: Final = frozenset(["a"])\n', id="frozenset-list"),
        pytest.param('KEYS: Final = frozenset(("a",))\n', id="frozenset-tuple"),
        pytest.param(
            'KINDS: Final = ("a",)\nKEYS: Final = frozenset(KINDS)\n',
            id="frozenset-constant-name",
        ),
        pytest.param('NAME: Final = "a"\nLABEL: Final = f"{NAME}-b"\n', id="f-string"),
        pytest.param(_FORMAT_SPEC, id="f-string-format-spec"),
        pytest.param("if a:\n    LIMIT: Final = 3\n", id="inside-if"),
        pytest.param(_LONG_CHAIN, id="long-operator-chain"),
    ],
)
def test_check_skips_final_constants(parse: Parse, source: str) -> None:
    assert mutableglobal.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("ITEMS: Final = [1]\n", _diags(1), id="list"),
        pytest.param('TABLE: Final = {"k": 1}\n', _diags(1), id="dict"),
        pytest.param("ITEMS: Final = {1}\n", _diags(1), id="set"),
        pytest.param("ITEMS: Final = (1, [2])\n", _diags(1), id="tuple-with-list"),
        pytest.param('PATTERN: Final = re.compile("a")\n', _diags(1), id="call"),
        pytest.param('ERROR: Final = LookupError("x")\n', _diags(1), id="exception"),
        pytest.param(
            "ITEMS: Final = frozenset([[1]])\n", _diags(1), id="frozenset-list"
        ),
        pytest.param(
            'KEYS: Final = frozenset(a for a in "b")\n', _diags(1), id="frozenset-gen"
        ),
        pytest.param("FLAG: Final = make() == 1\n", _diags(1), id="comparison-call"),
        pytest.param(
            "ITEMS: Final = [] if DEBUG else ()\n", _diags(1), id="conditional-list"
        ),
        pytest.param("VALUE: Final = make().value\n", _diags(1), id="call-attribute"),
        pytest.param(
            "VALUE: Final = make().a.b\n", _diags(1), id="nested-call-attribute"
        ),
        pytest.param("FIRST: Final = ITEMS[0]\n", _diags(1), id="subscript"),
        pytest.param('LABEL: Final = f"{make()}"\n', _diags(1), id="f-string-call"),
        pytest.param("LIMIT: Final\n", _diags(1), id="no-value"),
    ],
)
def test_check_reports_finals_that_are_not_constants(
    parse: Parse, source: str, expected: list[Diagnostic]
) -> None:
    assert mutableglobal.check(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("counter = 0  # nolint: mutableglobal\n", id="binding-line"),
        pytest.param("# nolint: mutableglobal\ncounter = 0\n", id="line-above"),
        pytest.param('__all__ = ["run"]  # nolint: mutableglobal\n', id="dunder-all"),
        pytest.param(_MULTILINE_NOLINT, id="line-above-multiline-binding"),
    ],
)
def test_check_skips_name_with_nolint(parse: Parse, source: str) -> None:
    assert mutableglobal.check(parse(source)) == []


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param("counter = 0  # nolint: varname\n", 1, id="other-rule"),
        pytest.param(
            "first = 0  # nolint: mutableglobal\nsecond = 0\n", 2, id="code-line-above"
        ),
        pytest.param(
            "# nolint: mutableglobal\n\ncounter = 0\n", 3, id="blank-line-between"
        ),
        pytest.param(
            "counter = 0\ncounter = 1  # nolint: mutableglobal\n", 1, id="later-binding"
        ),
    ],
)
def test_check_reports_name_without_its_nolint(
    parse: Parse, source: str, line: int
) -> None:
    assert mutableglobal.check(parse(source)) == _diags(line)
