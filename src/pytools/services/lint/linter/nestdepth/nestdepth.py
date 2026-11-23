import ast
from collections.abc import Iterator

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    elif_branch,
    functions,
)


def check(file: CheckInput, max_depth: int) -> list[Diagnostic]:
    """Report statements whose block nests past max_depth levels inside a function."""
    message = (
        f"nesting depth is {max_depth + 1} (limit {max_depth})"
        " — consider early returns or extracting a helper"
    )
    return [
        Diagnostic(file.path, stmt.lineno, message)
        for func in functions(file.tree)
        for stmt in _too_deep(func.body, max_depth)
    ]


def _too_deep(body: list[ast.stmt], levels_left: int) -> Iterator[ast.stmt]:
    # A statement over the limit is reported once and not entered.
    for stmt in body:
        blocks = _nested_blocks(stmt)
        if blocks and levels_left == 0:
            yield stmt
            continue
        for block in blocks:
            yield from _too_deep(block, levels_left - 1)


def _nested_blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(stmt, ast.If):
        return _if_chain_blocks(stmt)
    if isinstance(stmt, ast.For | ast.AsyncFor | ast.While):
        return [stmt.body, stmt.orelse]
    if isinstance(stmt, ast.With | ast.AsyncWith):
        return [stmt.body]
    if isinstance(stmt, ast.Try | ast.TryStar):
        handlers = [handler.body for handler in stmt.handlers]
        return [stmt.body, *handlers, stmt.orelse, stmt.finalbody]
    if isinstance(stmt, ast.Match):
        return [branch.body for branch in stmt.cases]
    return []


def _if_chain_blocks(stmt: ast.If) -> list[list[ast.stmt]]:
    # A loop, not recursion, so a long elif chain can't hit the recursion limit.
    blocks = [stmt.body]
    while (branch := elif_branch(stmt)) is not None:
        stmt = branch
        blocks.append(stmt.body)
    blocks.append(stmt.orelse)
    return blocks
