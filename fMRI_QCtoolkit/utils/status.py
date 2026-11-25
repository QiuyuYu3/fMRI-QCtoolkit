"""
Status assignment for quality control metrics
"""

import operator
import re

import pandas as pd

_OPERATORS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt,
              "==": operator.eq, "!=": operator.ne}
_SYMBOLS = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
_NEGATED = {">": "<=", ">=": "<", "<": ">=", "<=": ">", "==": "!=", "!=": "=="}
_RULE = re.compile(r"\s*(>=|<=|==|!=|>|<)\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*")
UPWARD = {">", ">="}
DOWNWARD = {"<", "<="}
# The rules a metric can have, as named in the config; "other" is whatever meets neither
RULE_TIERS = ("good", "bad")


def parse_rule(text):
    """'>= 0.2' -> ('>=', 0.2); anything else raises ValueError."""
    match = _RULE.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"{text!r} is not a rule; write an operator (>, >=, <, <=, ==, !=) "
                         f"followed by a number, such as '>= 0.2'")
    return match.group(1), float(match.group(2))


def format_number(value):
    """Shortest text that reads back as the same float: 15.0 -> '15', 0.15 -> '0.15'."""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def format_rule(rule, symbols=False):
    op, value = rule
    return f"{_SYMBOLS[op] if symbols else op} {format_number(value)}"


def negate_rule(rule):
    """The rule a value meets exactly when it does not meet `rule`: ('>', 15) -> ('<=', 15)."""
    op, value = rule
    return _NEGATED[op], value


def assign_status(values, rules):
    """'bad' where a value meets rules['bad'], 'good' where it meets rules['good'] (with no good rule, wherever it is
    not bad), 'other' where it meets neither; missing is 'NA'."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").astype(float)
    status = pd.Series("good" if "good" not in rules else "other", index=values.index, dtype=object)
    for tier in ("good", "bad"):
        if tier in rules:
            op, threshold = rules[tier]
            status[_OPERATORS[op](values, threshold).to_numpy()] = tier
    status[values.isna().to_numpy()] = "NA"
    return status


def _probes(rules):
    """One value in every stretch of the number line that the rules' thresholds mark off."""
    cuts = sorted({value for _, value in rules.values()})
    if not cuts:
        return []
    return [cuts[0] - 1, *cuts, *[(a + b) / 2 for a, b in zip(cuts, cuts[1:])], cuts[-1] + 1]


def rated_tiers(rules):
    """The statuses a metric's rules can give, in good, other, bad order; none for a metric without rules."""
    found = set(assign_status(_probes(rules), rules)) if rules else set()
    return [tier for tier in ("good", "other", "bad") if tier in found]


def describe_other(rules):
    """The values rated other, such as '15 < x ≤ 25'; None if the rules rate nothing other."""
    if "other" not in rated_tiers(rules):
        return None
    conditions = [negate_rule(rule) for rule in rules.values()]
    lower = [c for c in conditions if c[0] in UPWARD]
    upper = [c for c in conditions if c[0] in DOWNWARD]
    if len(lower) == 1 and len(upper) == 1:
        (low_op, low), (up_op, up) = lower[0], upper[0]
        return f"{format_number(low)} {'<' if low_op == '>' else '≤'} x {_SYMBOLS[up_op]} {format_number(up)}"
    return " and ".join(f"x {format_rule(c, symbols=True)}" for c in conditions)


def overlap(good, bad):
    """A value that meets both the good and the bad rule, or None."""
    for value in _probes({"good": good, "bad": bad}):
        if _OPERATORS[good[0]](value, good[1]) and _OPERATORS[bad[0]](value, bad[1]):
            return value
    return None


def get_status_mapping():
    """
    Get numerical mapping for status values.
    """
    return {'NA': 0, 'bad': 1, 'other': 2, 'good': 3}


def get_status_colors():
    """
    Get color mapping for status values.
    """
    return {
        0: '#D3D3D3',  # NA - light gray
        1: '#F8786E',  # bad - red
        2: '#FFD966',  # other - yellow
        3: '#C5E0B3'   # good - green
    }
