from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.names import (
    DeclaredName,
    NameKind,
    declared_names,
)
from pytools.services.lint.linter.analysis.nolint import has_name_nolint

_MAX_NAME_LEN: Final = 30
_MAX_LOCAL_NAME_LEN: Final = 20
_MAX_TEST_NAME_LEN: Final = 50


def check(file: CheckInput) -> list[Diagnostic]:
    """Report names longer than their limit, at each one's first binding in a scope."""
    diags = [_check_name(file, name) for name in declared_names(file)]
    return [diag for diag in diags if diag is not None]


def _check_name(file: CheckInput, name: DeclaredName) -> Diagnostic | None:
    limit = _name_limit(name.kind)
    length = len(name.text)
    if length <= limit:
        return None
    if has_name_nolint(file, name, Rule.NAMELEN):
        return None
    message = f'name "{name.text}" is {length} chars (limit {limit})'
    return Diagnostic(file.path, name.line, message)


def _name_limit(kind: NameKind) -> int:
    if kind in (NameKind.LOCAL_VAR, NameKind.TYPE_PARAM):
        return _MAX_LOCAL_NAME_LEN
    if kind is NameKind.TEST_FUNC:
        return _MAX_TEST_NAME_LEN
    return _MAX_NAME_LEN
