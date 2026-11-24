from collections.abc import Callable
from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput
from pytools.services.lint.linter.funcorder import model
from pytools.services.lint.linter.funcorder.classes import Classes, Use

type Parse = Callable[[str], CheckInput]

_CLASS_CHAIN: Final = """\
C = 1
class Q:
    x = C
class P(Q): pass
def run(p: P): pass
"""
_USER_STAYS: Final = """\
def make(): return Line()
X = 1
class Point:
    x: int
class Line:
    start: Point
    y = X
"""


def test_find_classes_chains_methodless_class_needs(parse: Parse) -> None:
    plain_needs = _find(parse, _CLASS_CHAIN).plain_needs
    assert plain_needs == {1: frozenset({0}), 2: frozenset({0, 1})}


def test_find_classes_places_users_that_stay(parse: Parse) -> None:
    found = _find(parse, _USER_STAYS)
    expected = ({2: Use(3, 3, 0), 3: Use(0, 0, 0)}, frozenset({2}))
    assert (found.uses, found.movable) == expected


def _find(parse: Parse, source: str) -> Classes:
    file = parse(source)
    return model.build(file, file.tree).classes
