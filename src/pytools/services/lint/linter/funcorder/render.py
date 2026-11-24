import ast
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    header_end,
    is_body_tail,
    is_code_line,
    module_header_end,
    start_line,
)


def has_shared_lines(file: CheckInput, scope: ast.Module | ast.ClassDef) -> bool:
    """Report whether a statement in scope starts on a line with code above it."""
    ends = _ends(file, scope)
    pairs = zip(scope.body, ends[:-1], strict=True)
    return any(start_line(stmt) <= end for stmt, end in pairs)


def render(file: CheckInput, orders: dict[ast.Module | ast.ClassDef, list[int]]) -> str:
    """Return file's source with each scope's statements laid out in its order.

    A statement moves with the comments and blank lines above it.
    """
    found = (_region(file, scope, order) for scope, order in orders.items())
    regions = sorted(found, key=lambda region: region.chunks[0].start)
    return "\n".join(_render_lines(file, regions, range(1, len(file.lines) + 1)))


@dataclass(frozen=True)
class _Region:
    """A scope's statements as line ranges, and the order to lay them out in."""

    chunks: list[range]  # each statement, with the comments directly above it
    order: list[int]


def _region(
    file: CheckInput, scope: ast.Module | ast.ClassDef, order: list[int]
) -> _Region:
    ends = _ends(file, scope)
    pairs = zip(scope.body, ends[:-1], strict=True)
    starts = [_chunk_start(file, stmt, end) for stmt, end in pairs]
    chunks = [
        range(start, end + 1) for start, end in zip(starts, ends[1:], strict=True)
    ]
    return _Region(chunks, order)


def _ends(file: CheckInput, scope: ast.Module | ast.ClassDef) -> list[int]:
    """Return the line each statement in scope ends on, after the scope's header's.

    The lines above a module's first statement are its header and stay put.
    """
    if isinstance(scope, ast.ClassDef):
        header = header_end(file, scope)
    else:
        header = module_header_end(file) - 1
    return [header, *(_end_line(file, stmt) for stmt in scope.body)]


def _end_line(file: CheckInput, stmt: ast.stmt) -> int:
    """Return stmt's last line, past the lines a backslash joins to it.

    The comments indented under it after its last line belong to it too.
    """
    end = stmt.end_lineno or stmt.lineno
    while end < len(file.lines) and _is_continued(file, end):
        end += 1
    last = end
    while last < len(file.lines) and is_body_tail(file, last + 1, stmt.col_offset):
        last += 1
        end = last if last in file.comments else end
    return end


def _is_continued(file: CheckInput, number: int) -> bool:
    is_code = number not in file.comments
    return is_code and file.lines[number - 1].rstrip().endswith("\\")


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
        start, stop = region.chunks[0].start, region.chunks[-1].stop
        if start < line or stop > lines.stop:
            continue
        out.extend(file.lines[line - 1 : start - 1])
        out.extend(_render_region(file, regions, region))
        line = stop
    out.extend(file.lines[line - 1 : lines.stop - 1])
    return out


def _render_region(
    file: CheckInput, regions: list[_Region], region: _Region
) -> list[str]:
    """Return the region's chunks in its order, each with the lines above it.

    The first chunk has none: what sits above it stays above the region.
    """
    chunks = region.chunks
    out: list[str] = []
    for idx in region.order:
        gap_start = chunks[idx - 1].stop if idx else chunks[0].start
        out.extend(file.lines[gap_start - 1 : chunks[idx].start - 1])
        out.extend(_render_lines(file, regions, chunks[idx]))
    return out
