from collections.abc import Callable
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.classes import Classes

type Parse = Callable[[str], CheckInput]

_CLASS_CHAIN: Final = """\
C = 1
class Q:
    x = C
class P(Q): pass
def run(p: P): pass
"""


def test_find_classes_chains_methodless_class_needs(parse: Parse) -> None:
    plain_needs = _find(parse, _CLASS_CHAIN).plain_needs
    assert plain_needs == {1: frozenset({0}), 2: frozenset({0, 1})}


def _find(parse: Parse, source: str) -> Classes:
    file = parse(source)
    return model.build(file, file.tree).classes
