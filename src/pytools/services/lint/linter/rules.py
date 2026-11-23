from collections.abc import Callable
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.funclen import funclen


@dataclass(frozen=True)
class Config:
    """Custom linter configuration."""

    max_func_len: int
    exclude: frozenset[Rule]


def run_checks(file: CheckInput, config: Config) -> list[Diagnostic]:
    """Run every rule the config does not exclude on one parsed file."""
    diags: list[Diagnostic] = []
    for rule, check in _rule_checkers(config).items():
        if rule not in config.exclude:
            diags.extend(check(file))
    return diags


def _rule_checkers(
    config: Config,
) -> dict[Rule, Callable[[CheckInput], list[Diagnostic]]]:
    return {
        Rule.FUNCLEN: lambda file: funclen.check(file, config.max_func_len),
    }
