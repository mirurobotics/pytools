from dataclasses import dataclass

from pytools.services.lint.linter.rules import Config, Rule, parse_rule


@dataclass(frozen=True)
class LinterFlags:
    """The custom linter's flag values."""

    max_func_len: int
    exclude: str
    rule: str | None


def build_linter_config(flags: LinterFlags) -> Config:
    """Build the linter config, raising UnknownRuleError for an unknown rule name."""
    exclude = _parse_exclusions(flags.exclude)
    if flags.rule is not None:
        exclude = _build_single_rule_exclusions(flags.rule)
    return Config(max_func_len=flags.max_func_len, exclude=exclude)


def _parse_exclusions(csv: str) -> frozenset[Rule]:
    if not csv:
        return frozenset()
    return frozenset(parse_rule(name.strip()) for name in csv.split(","))


def _build_single_rule_exclusions(name: str) -> frozenset[Rule]:
    return frozenset(Rule) - {parse_rule(name)}
