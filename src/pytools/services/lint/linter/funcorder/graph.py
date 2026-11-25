# Following every reference may pin more than needed, but never too little.
def import_time_reach(
    loads: set[str], names: dict[str, int], refs: dict[int, list[int]]
) -> set[int]:
    """Return the decls a statement loads at import time, and all they refer to."""
    used = {names[name] for name in loads if name in names}
    return used.union(*(reachable(refs, idx) for idx in used))


def reachable(callees: dict[int, list[int]], start: int) -> set[int]:
    seen: set[int] = set()
    pending = list(callees[start])
    while pending:
        idx = pending.pop()
        if idx not in seen:
            seen.add(idx)
            pending.extend(callees[idx])
    return seen


# The rule would move such a decl below that caller, past the use. A def counts as
# below its own decorators and defaults.
def pinned(import_time: list[set[int]], reach: dict[int, set[int]]) -> set[int]:
    """Return the decls an import-time use needs that a caller below it reaches."""
    last = {idx: caller for caller in sorted(reach) for idx in reach[caller]}
    return {
        idx
        for use, needed in enumerate(import_time)
        for idx in needed
        if last.get(idx, -1) >= use
    }


def components(reach: dict[int, set[int]]) -> dict[int, int]:
    """Label each def with its cycle's first member, or itself outside a cycle."""
    return {
        idx: min([idx, *(other for other in reach[idx] if idx in reach[other])])
        for idx in reach
    }


def callers_of(
    calls: dict[int, list[int]], comps: dict[int, int], idx: int, *, in_cycle: bool
) -> list[int]:
    return [
        caller
        for caller, found in calls.items()
        if idx in found and (comps[caller] == comps[idx]) == in_cycle
    ]


def above(edges: dict[int, frozenset[int]]) -> dict[int, frozenset[int]]:
    """Return each node's edges to nodes before it."""
    return {
        idx: frozenset(other for other in found if other < idx)
        for idx, found in edges.items()
    }
