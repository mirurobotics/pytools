from typing import Final

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.analysis.names import (
    DeclaredName,
    NameKind,
    declared_names,
)
from pytools.services.lint.linter.analysis.nolint import has_name_nolint

_MIN_NAME_LEN: Final = 3

_ALLOWED: Final = frozenset({"_", "i", "a", "b", "ok", "id", "db"})
_VARIABLES: Final = frozenset({NameKind.MODULE_VAR, NameKind.LOCAL_VAR})


def check(file: CheckInput) -> list[Diagnostic]:
    """Report parameters and variables whose names are too short to read."""
    diags = [_check_name(file, name) for name in declared_names(file)]
    return [diag for diag in diags if diag is not None]


def _check_name(file: CheckInput, name: DeclaredName) -> Diagnostic | None:
    if name.kind not in _VARIABLES or not _is_too_short(name.text):
        return None
    if has_name_nolint(file, name, Rule.VARNAME):
        return None
    message = (
        f'variable name "{name.text}" is shorter than {_MIN_NAME_LEN} chars;'
        " use a descriptive name"
    )
    return Diagnostic(file.path, name.line, message)


def _is_too_short(text: str) -> bool:
    return len(text) < _MIN_NAME_LEN and text not in _ALLOWED
