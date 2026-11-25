"""
Status assignment for quality control metrics
"""

import operator
import re

import pandas as pd

_OPERATORS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt,
              "==": operator.eq, "!=": operator.ne}
_SYMBOLS = {">=": "≥", "<=": "≤", "!=": "≠", "==": "=", ">": ">", "<": "<"}
_RULE = re.compile(r"\s*(>=|<=|==|!=|>|<)\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*")
UPWARD = {">", ">="}
DOWNWARD = {"<", "<="}


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


def assign_status(values, rules):
    """'bad' where a value meets rules['bad'], else 'other' where it meets rules['other'], else 'good'; missing is 'NA'."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").astype(float)
    status = pd.Series("good", index=values.index, dtype=object)
    for tier in ("other", "bad"):
        if tier in rules:
            op, threshold = rules[tier]
            status[_OPERATORS[op](values, threshold).to_numpy()] = tier
    status[values.isna().to_numpy()] = "NA"
    return status


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
