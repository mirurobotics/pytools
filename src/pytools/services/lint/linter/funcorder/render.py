import ast
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    header_end,
    is_code_line,
    start_line,
)


def has_shared_lines(file: CheckInput, scope: ast.Module | ast.ClassDef) -> bool:
    """Report whether a statement in scope starts on a line with code above it."""
    ends = _ends(file, scope)
    pairs = zip(scope.body, ends[:-1], strict=True)
    return any(start_line(stmt) <= end for stmt, end in pairs)


def render(file: CheckInput, orders: dict[ast.Module | ast.ClassDef, list[int]]) -> str:
    """Return file's source with each scope's statements laid out in its order.

    A statement moves with the comments above it, and gets blank lines above it
    that ruff format accepts.
    """
    found = (_region(file, scope, order) for scope, order in orders.items())
    regions = sorted(found, key=lambda region: region.lines.start)
    return "\n".join(_render_lines(file, regions, range(1, len(file.lines) + 1)))


@dataclass(frozen=True)
class _Region:
    """A scope's statements as line ranges, and the order to lay them out in."""

    lines: range
    chunks: list[range]  # each statement, with the comments directly above it
    gaps: list[range]  # the lines between each chunk and the one before it
    order: list[int]
    is_def: list[bool]
    blank: int  # the blank lines ruff format puts around a def in the scope


def _region(
    file: CheckInput, scope: ast.Module | ast.ClassDef, order: list[int]
) -> _Region:
    ends = _ends(file, scope)
    pairs = zip(scope.body, ends[:-1], strict=True)
    starts = [_chunk_start(file, stmt, end) for stmt, end in pairs]
    chunks = [
        range(start, end + 1) for start, end in zip(starts, ends[1:], strict=True)
    ]
    gaps = [range(end + 1, start) for end, start in zip(ends[:-1], starts, strict=True)]
    gaps[0] = range(starts[0], starts[0])
    is_def = [
        isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        for stmt in scope.body
    ]
    blank = 2 if isinstance(scope, ast.Module) else 1
    lines = range(starts[0], ends[-1] + 1)
    return _Region(lines, chunks, gaps, order, is_def, blank)


def _ends(file: CheckInput, scope: ast.Module | ast.ClassDef) -> list[int]:
    """Return the line each statement in scope ends on, after the scope's header's."""
    header = header_end(file, scope) if isinstance(scope, ast.ClassDef) else 0
    return [header, *(stmt.end_lineno or stmt.lineno for stmt in scope.body)]


def _chunk_start(file: CheckInput, stmt: ast.stmt, floor: int) -> int:
    """Return the first line of stmt and the comments directly above it."""
    line = start_line(stmt)
    while line - 1 > floor and _is_comment_only(file, line - 1):
        line -= 1
    return line


def _is_comment_only(file: CheckInput, number: int) -> bool:
    return number in file.comments and not is_code_line(file, number)


def _render_lines(file: CheckInput, regions: list[_Region], lines: range) -> list[str]:
    """Return lines, each region in them laid out in its order."""
    out: list[str] = []
    line = lines.start
    for region in regions:
        if region.lines.start < line or region.lines.stop > lines.stop:
            continue
        out.extend(file.lines[line - 1 : region.lines.start - 1])
        out.extend(_render_region(file, regions, region))
        line = region.lines.stop
    out.extend(file.lines[line - 1 : lines.stop - 1])
    return out


def _render_region(
    file: CheckInput, regions: list[_Region], region: _Region
) -> list[str]:
    out: list[str] = []
    prev: int | None = None
    for idx in region.order:
        out.extend(_separator(file, region, prev, idx))
        out.extend(_render_lines(file, regions, region.chunks[idx]))
        prev = idx
    return out


def _separator(
    file: CheckInput, region: _Region, prev: int | None, idx: int
) -> list[str]:
    """Return the lines to put above chunk idx when it follows chunk prev.

    A chunk that still follows the one it did keeps its gap. Otherwise the gap's
    comments go with it, below the blank lines ruff format and isort accept.
    """
    gap = region.gaps[idx]
    found = file.lines[gap.start - 1 : gap.stop - 1]
    if prev == idx - 1:
        return found
    blanks = next((pos for pos, line in enumerate(found) if line.strip()), len(found))
    if prev is None:
        return found[blanks:]
    is_def = region.is_def[prev] or region.is_def[idx]
    return [""] * (region.blank if is_def else 1) + found[blanks:]
