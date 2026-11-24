import ast
from typing import TypeGuard

from pytools.services.lint.linter.analysis.analysis import ROOTS, Function
from pytools.services.lint.linter.analysis.names import outer_parts, param_defaults


def loaded_nodes(nodes: list[ast.AST], body: set[ast.AST]) -> set[ast.AST]:
    """Return the nodes only loaded, running none of their code.

    In a class body, only the parts of an annotation can be, since the body may
    run code on any value it binds or iterates. Anywhere, a list or tuple's
    elements are only if it is, since a callee can run them. Nodes come
    parents first.
    """
    loaded: set[ast.AST] = set()
    for node in nodes:
        is_root = isinstance(node, (ast.AnnAssign, *ROOTS))
        is_gated = node in body or isinstance(node, (ast.List, ast.Tuple))
        if not is_gated or node in loaded or is_root:
            loaded.update(_loaded_parts(node, in_body=node in body))
    return loaded


def _loaded_parts(node: ast.AST, *, in_body: bool) -> list[ast.AST]:
    """Return the parts of node it only loads, running none of their code.

    Those are an annotation, a default, a list or tuple element, and a
    subscript slice of a name or attribute, such as `list[Vec]`. A call
    argument may run, since the callee can call it.
    """
    if isinstance(node, ast.AnnAssign):
        return [node.annotation]
    if isinstance(node, (ast.List, ast.Tuple)):
        return list(node.elts)
    if isinstance(node, ROOTS):
        return _loaded_def_parts(node, in_body=in_body)
    if isinstance(node, ast.Subscript) and _is_named(node.value):
        return [node.slice]
    return []


def _loaded_def_parts(node: Function | ast.Lambda, *, in_body: bool) -> list[ast.AST]:
    """Return a def's or lambda's annotations, setter's def and defaults.

    In a class body, a default pins the class too, which is deliberately
    conservative.
    """
    defaults = param_defaults(node.args)
    if isinstance(node, ast.Lambda):
        return [] if in_body else defaults
    decorators = node.decorator_list
    skipped = [*decorators, *defaults] if in_body else decorators
    loaded = [part for part in outer_parts(node) if part not in skipped]
    replaced = [dec.value for dec in decorators if _is_on(dec, node.name)]
    return [*loaded, *replaced]


def _is_on(decorator: ast.expr, name: str) -> TypeGuard[ast.Attribute]:
    value = decorator.value if isinstance(decorator, ast.Attribute) else None
    return isinstance(value, ast.Name) and value.id == name


def _is_named(node: ast.expr) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name)
