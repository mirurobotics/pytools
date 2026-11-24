import ast
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import DEFS, CheckInput, Function
from pytools.services.lint.linter.funcorder import graph
from pytools.services.lint.linter.funcorder.decl import Decl, DeclKind
from pytools.services.lint.linter.funcorder.refs import called_names

type _Users = dict[int, list[int]]


@dataclass(frozen=True)
class Classes:
    """Where the classes directly in a scope go."""

    plain: _Users  # the users of each used class without methods
    plain_needs: dict[int, frozenset[int]]  # needs, with those of classes it uses
    tucked: _Users  # the defs above each class with methods that use it


def find_classes(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    refs: dict[int, list[int]],
    loads: list[set[str]],
    needs: dict[int, frozenset[int]],
) -> Classes:
    """Return where the classes in scope go, from the statements that use them."""
    users = _users(file, scope, decls, refs, loads)
    used = {cls: found for cls, found in users.items() if found}
    plain = _plain(decls, used)
    return Classes(plain, _plain_needs(plain, needs), _tucked(decls, used))


def _users(
    file: CheckInput,
    scope: ast.Module | ast.ClassDef,
    decls: dict[int, Decl],
    refs: dict[int, list[int]],
    loads: list[set[str]],
) -> _Users:
    """Return the statements that refer to each class, when run or when called.

    The stubs merged into a decl refer for it.
    """
    names = {decl.stmt.name: idx for idx, decl in decls.items()}
    merged = {
        stub: idx for idx, decl in decls.items() for stub in range(decl.first, idx)
    }
    referred = [set(refs.get(idx, [])) for idx in range(len(scope.body))]
    for idx, stmt in enumerate(scope.body):
        named = set(loads[idx])
        if idx not in decls and idx not in merged:
            named.update(called_names(file, scope, stmt))
        owner = merged.get(idx, idx)
        referred[owner].update(names[name] for name in named if name in names)
    return {
        cls: [idx for idx, found in enumerate(referred) if cls in found and idx != cls]
        for cls, decl in decls.items()
        if decl.kind is DeclKind.CLASS
    }


def _plain(decls: dict[int, Decl], users: _Users) -> _Users:
    """Return the users of each class without methods.

    Such classes that use each other in a cycle are left out, since none of
    them has a first user to go above.
    """
    plain = {cls: found for cls, found in users.items() if not _has_methods(decls[cls])}
    within = {
        cls: [user for user in found if user in plain] for cls, found in plain.items()
    }
    return {
        cls: found
        for cls, found in plain.items()
        if cls not in graph.reachable(within, cls)
    }


def _plain_needs(
    plain: _Users, needs: dict[int, frozenset[int]]
) -> dict[int, frozenset[int]]:
    """Return what each class without methods needs when defined.

    The classes it uses go above it, so what they need counts as its own.
    """
    uses = {cls: [other for other in plain if cls in plain[other]] for cls in plain}
    return {
        cls: needs[cls].union(*(needs[other] for other in graph.reachable(uses, cls)))
        for cls in plain
    }


def _tucked(decls: dict[int, Decl], users: _Users) -> _Users:
    """Return the defs above each class with methods that use it."""
    defs = {idx for idx, decl in decls.items() if decl.kind is not DeclKind.CLASS}
    above = {
        cls: [user for user in found if user < cls and user in defs]
        for cls, found in users.items()
        if _has_methods(decls[cls])
    }
    return {cls: found for cls, found in above.items() if found}


def _has_methods(decl: Decl) -> bool:
    """Report whether decl has a def with more than a docstring or `...`."""
    return any(isinstance(stmt, DEFS) and _has_body(stmt) for stmt in decl.stmt.body)


def _has_body(func: Function) -> bool:
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    return not all(
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
        for stmt in body
    )
