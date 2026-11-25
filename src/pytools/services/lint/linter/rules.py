from collections.abc import Callable
from dataclasses import dataclass

from pytools.services.lint.linter.analysis.analysis import CheckInput, Diagnostic, Rule
from pytools.services.lint.linter.commentedcode import commentedcode
from pytools.services.lint.linter.fieldassert import fieldassert
from pytools.services.lint.linter.filelen import filelen
from pytools.services.lint.linter.funccomment import funccomment
from pytools.services.lint.linter.funclen import funclen
from pytools.services.lint.linter.funcorder import funcorder
from pytools.services.lint.linter.mutableglobal import mutableglobal
from pytools.services.lint.linter.namelen import namelen
from pytools.services.lint.linter.nestdepth import nestdepth
from pytools.services.lint.linter.straycomment import straycomment
from pytools.services.lint.linter.varname import varname


@dataclass(frozen=True)
class Config:
    """Custom linter configuration."""

    max_func_len: int = 30
    max_file_len: int = 300
    max_nest_depth: int = 2
    exclude: frozenset[Rule] = frozenset()


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
        Rule.FILELEN: lambda file: filelen.check(file, config.max_file_len),
        Rule.NESTDEPTH: lambda file: nestdepth.check(file, config.max_nest_depth),
        Rule.NAMELEN: namelen.check,
        Rule.VARNAME: varname.check,
        Rule.STRAYCOMMENT: straycomment.check,
        Rule.FUNCCOMMENT: funccomment.check,
        Rule.COMMENTEDCODE: commentedcode.check,
        Rule.MUTABLEGLOBAL: mutableglobal.check,
        Rule.FUNCORDER: funcorder.check,
        Rule.FIELDASSERT: fieldassert.check,
    }
