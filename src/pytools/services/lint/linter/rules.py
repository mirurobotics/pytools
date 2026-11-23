import ast
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pytools.services.lint.linter.analysis.analysis import Diagnostic
from pytools.services.lint.linter.funclen import funclen


class Rule(StrEnum):
    """A custom linter rule name."""

    FUNCLEN = "funclen"


class UnknownRuleError(ValueError):
    """A rule name that matches no Rule."""


@dataclass(frozen=True)
class Config:
    """Custom linter configuration."""

    max_func_len: int
    exclude: frozenset[Rule]


def parse_rule(name: str) -> Rule:
    """Return the rule called name, raising UnknownRuleError if there is none."""
    try:
        return Rule(name)
    except ValueError as err:
        raise UnknownRuleError(f"unknown lint rule: {name!r}") from err


@dataclass(frozen=True)
class CheckInput:
    """One parsed file for the rule checks."""

    path: str
    tree: ast.Module
    source: str


def run_checks(check_input: CheckInput, config: Config) -> list[Diagnostic]:
    """Run every rule the config does not exclude on one parsed file."""
    diags: list[Diagnostic] = []
    for entry in _rule_checkers(config):
        if entry.rule not in config.exclude:
            diags.extend(entry.check(check_input))
    return diags


@dataclass(frozen=True)
class _RuleEntry:
    rule: Rule
    check: Callable[[CheckInput], list[Diagnostic]]


def _rule_checkers(config: Config) -> list[_RuleEntry]:
    return [
        _RuleEntry(
            Rule.FUNCLEN,
            lambda parsed: funclen.check(
                parsed.path, parsed.tree, parsed.source, config.max_func_len
            ),
        ),
    ]
