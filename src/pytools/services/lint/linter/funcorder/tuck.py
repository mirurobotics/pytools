from pytools.services.lint.linter.funcorder.model import Model


def tuck(model: Model, trees: list[list[int]], waits: dict[int, set[int]]) -> set[int]:
    """Move each class with methods below the call tree of its last user above it.

    Trees change in place. Return the classes moved, each now under that tree.
    """
    moved: set[int] = set()
    while (found := _next_tuck(model, trees, waits)) is not None:
        start, last = found
        tree = trees.pop(start)
        trees[last].extend(tree)
        moved.add(tree[0])
    return moved


def _next_tuck(
    model: Model, trees: list[list[int]], waits: dict[int, set[int]]
) -> tuple[int, int] | None:
    """Return the tree a class heads that can move, and the tree it moves under."""
    for cls in sorted(model.classes.tucked):
        start = next((pos for pos, tree in enumerate(trees) if tree[0] == cls), None)
        if start is None:
            continue
        last = _last_user_tree(model, trees[:start], cls)
        if last is not None and _is_tuckable(model, trees, waits, start, last):
            return start, last
    return None


def _last_user_tree(model: Model, trees: list[list[int]], cls: int) -> int | None:
    """Return the last of trees that holds a def above cls that uses it."""
    users = set(model.classes.tucked[cls])
    found = [pos for pos, tree in enumerate(trees) if not users.isdisjoint(tree)]
    return max(found, default=None)


def _is_tuckable(
    model: Model,
    trees: list[list[int]],
    waits: dict[int, set[int]],
    start: int,
    last: int,
) -> bool:
    """Report whether the tree at start can move up under the tree at last.

    It can't hold a statement, which runs in order at import time, and in the
    file the class must rise below that tree's end without passing what it uses
    when defined. Nor can a tree it passes hold what it waits for or a caller.
    """
    tree, end = trees[start], trees[last][-1]
    if any(idx not in model.decls and idx not in model.stubs for idx in tree):
        return False
    if not max(model.needs[tree[0]], default=-1) < end < tree[0]:
        return False
    passed = {idx for between in trees[last + 1 : start] for idx in between}
    waited = {need for idx in tree for need in waits.get(idx, set())}
    callers = {caller for idx in tree for caller in model.callers.get(idx, [])}
    return passed.isdisjoint(waited | callers)
