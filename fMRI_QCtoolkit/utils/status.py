"""
Status assignment for quality control metrics
"""

import math
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
# The levels a metric can give a run, best first
LEVELS = ("good", "other", "bad")


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


def rest_tier(rules, otherwise=None):
    """The level of a value that meets neither rule: `otherwise` if set, else other with a good rule, else good."""
    return otherwise or ("other" if "good" in rules else "good")


def assign_status(values, rules, otherwise=None):
    """'good' where a value meets rules['good'], 'bad' where it meets rules['bad'], and rest_tier where it meets
    neither; missing is 'NA'."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").astype(float)
    status = pd.Series(rest_tier(rules, otherwise), index=values.index, dtype=object)
    for tier in RULE_TIERS:
        if tier in rules:
            op, threshold = rules[tier]
            status[_OPERATORS[op](values, threshold).to_numpy()] = tier
    status[values.isna().to_numpy()] = "NA"
    return status


def _probes(rules):
    """One value in every stretch of the number line that the rules' thresholds mark off."""
    cuts = sorted({value for _, value in rules.values()})
    if not cuts:
        return [0.0]
    return [cuts[0] - 1, *cuts, *[(a + b) / 2 for a, b in zip(cuts, cuts[1:])], cuts[-1] + 1]


def rated_tiers(rules, otherwise=None):
    """The levels a metric can give, in good, other, bad order; none for a metric that is not rated."""
    if not rules and otherwise is None:
        return []
    found = set(assign_status(_probes(rules), rules, otherwise))
    return [tier for tier in LEVELS if tier in found]


def _segments(rules):
    """The stretches of the number line at and between the thresholds, as (low, high, closed_low, closed_high)."""
    cuts = sorted({value for _, value in rules.values()})
    if not cuts:
        return [(-math.inf, math.inf, False, False)]
    segments = [(-math.inf, cuts[0], False, False)]
    for a, b in zip(cuts, cuts[1:] + [math.inf]):
        segments += [(a, a, True, True), (a, b, False, False)]
    return segments


def _representative(segment):
    low, high = segment[:2]
    if low == high:
        return low
    if math.isinf(low) and math.isinf(high):
        return 0.0
    return high - 1 if math.isinf(low) else low + 1 if math.isinf(high) else (low + high) / 2


def _interval_text(low, high, closed_low, closed_high):
    if low == high:
        return f"x = {format_number(low)}"
    if math.isinf(low) and math.isinf(high):
        return "all"
    if math.isinf(low):
        return f"x {'≤' if closed_high else '<'} {format_number(high)}"
    if math.isinf(high):
        return f"x {'≥' if closed_low else '>'} {format_number(low)}"
    return (f"{format_number(low)} {'≤' if closed_low else '<'} x "
            f"{'≤' if closed_high else '<'} {format_number(high)}")


def _region_text(intervals):
    """Text for a union of intervals, such as 'x ≤ 15' or 'x ≠ 0'."""
    holes = [a[1] for a, b in zip(intervals, intervals[1:])
             if a[1] == b[0] and not a[3] and not b[2]]
    if (math.isinf(intervals[0][0]) and math.isinf(intervals[-1][1]) and len(holes) == len(intervals) - 1
            and len(intervals) > 1):
        return " and ".join(f"x ≠ {format_number(h)}" for h in holes)
    return " or ".join(_interval_text(*interval) for interval in intervals)


def describe_levels(rules, otherwise=None):
    """{level: the values it covers}, such as {'good': 'x ≤ 15', 'other': '15 < x ≤ 20', 'bad': 'x > 20'}."""
    segments = _segments(rules)
    levels = assign_status([_representative(s) for s in segments], rules, otherwise).tolist()
    merged = []
    for segment, level in zip(segments, levels):
        if merged and merged[-1][0] == level:
            low, _, closed_low, _ = merged[-1][1]
            merged[-1] = (level, (low, segment[1], closed_low, segment[3]))
        else:
            merged.append((level, segment))
    regions = {}
    for level, interval in merged:
        regions.setdefault(level, []).append(interval)
    return {level: _region_text(regions[level]) for level in LEVELS if level in regions}


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
