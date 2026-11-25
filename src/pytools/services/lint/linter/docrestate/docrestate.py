import ast
import re
from typing import Final

from pytools.services.lint.linter.analysis.analysis import (
    CheckInput,
    Diagnostic,
    Function,
    Rule,
)
from pytools.services.lint.linter.analysis.nolint import has_nolint_on_lines

_QUOTED: Final = r"[\"`]|(?<!\w)'[^']+'"
_NAME_WORD: Final = r"[A-Z]+s(?![a-z])|[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+"
_MIN_STEM_LEN: Final = 4
_FILLER: Final = frozenset(
    {
        "a",
        "an",
        "are",
        "be",
        "build",
        "builds",
        "class",
        "construct",
        "constructs",
        "create",
        "creates",
        "for",
        "func",
        "function",
        "given",
        "instance",
        "interface",
        "is",
        "it",
        "its",
        "make",
        "makes",
        "method",
        "new",
        "object",
        "of",
        "return",
        "returns",
        "struct",
        "that",
        "the",
        "this",
        "type",
        "value",
    }
)


def check(file: CheckInput) -> list[Diagnostic]:
    """Report class and function docstrings that only restate the name they document."""
    owners = [
        node
        for node in ast.walk(file.tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    diags = [_check_docstring(file, owner) for owner in owners]
    found = [diag for diag in diags if diag is not None]
    return sorted(found, key=lambda diag: diag.line)


def _check_docstring(
    file: CheckInput, owner: Function | ast.ClassDef
) -> Diagnostic | None:
    first = owner.body[0]
    doc = ast.get_docstring(owner)
    if not isinstance(first, ast.Expr) or doc is None:
        return None
    if not _restates(owner.name, doc):
        return None
    string = first.value
    end = string.end_lineno or string.lineno
    if has_nolint_on_lines(file.comments, Rule.DOCRESTATE, string.lineno, end):
        return None
    message = (
        f"docstring for {owner.name} only restates its name; "
        "say what it does or remove it"
    )
    return Diagnostic(file.path, string.lineno, message)


def _restates(name: str, doc: str) -> bool:
    if _has_symbols(doc):
        return False
    words = re.findall(r"\w+", doc.lower())
    name_words = [word.lower() for word in re.findall(_NAME_WORD, name)]
    name_words.append(name.lower())
    others = [word for word in words if not _is_name_word(word, name_words)]
    return len(others) < len(words) and all(word in _FILLER for word in others)


def _has_symbols(doc: str) -> bool:
    if re.search(_QUOTED, doc):
        return True
    tokens = (token.strip(".,;:!?") for token in doc.split())
    return any(token and re.search(r"\w", token) is None for token in tokens)


def _is_name_word(word: str, name_words: list[str]) -> bool:
    return any(_inflects(word, base) or _inflects(base, word) for base in name_words)


def _inflects(word: str, base: str) -> bool:
    has_base = word.startswith(base)
    suffix = word[len(base) :]
    if has_base and _takes_short_suffix(base, suffix):
        return True
    if len(base) < _MIN_STEM_LEN:
        return False
    if has_base and suffix in ("ed", "ing"):
        return True
    stem = base[:-1]
    if base.endswith("e") and word == f"{stem}ing":
        return True
    return base.endswith("y") and word in (f"{stem}ies", f"{stem}ied")


def _takes_short_suffix(base: str, suffix: str) -> bool:
    if suffix in ("", "s"):
        return True
    if suffix == "es":
        return base.endswith(("s", "x", "z", "ch", "sh"))
    return suffix == "d" and base.endswith("e")
