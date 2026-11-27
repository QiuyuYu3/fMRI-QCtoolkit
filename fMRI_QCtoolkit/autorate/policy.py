"""
The autorate block of a config: how a run's numbers become section levels, and how sections become a decision
"""

import json
import re
from dataclasses import dataclass

from ..dashboard.config import ConfigError, default_config_path, parse_entry
from ..data.afni_pipeline import APQC_SECTIONS
from ..utils.status import DOWNWARD, UPWARD

# Sections the numbers settle; every other weighted section comes from the rater's APQC rating
NUMERIC_SECTIONS = ("qsumm", "mot", "warns")
RATED_SECTIONS = tuple(s for s in APQC_SECTIONS if s not in NUMERIC_SECTIONS and s != "FINAL")
_FIELDS = ("metrics", "mot", "warns", "weights", "veto_sections", "cutoffs", "margin", "lenient", "spot_check",
           "calibration")
_METRIC_FIELDS = ("tolerance", "veto")
_PERCENT = re.compile(r"\s*(\d+(?:\.\d*)?|\.\d+)\s*%\s*")


@dataclass(frozen=True)
class Tolerance:
    amount: float = 0.0
    # A share of the line the value crossed, rather than an amount in the metric's units
    relative: bool = False


@dataclass(frozen=True)
class MetricPolicy:
    tolerance: Tolerance = Tolerance()
    veto: bool = False


NO_POLICY = MetricPolicy()


@dataclass(frozen=True)
class Policy:
    metrics: dict
    mot: str
    warns_column: str
    warns: object
    weights: dict
    veto_sections: tuple
    cut_bad: float
    cut_other: float
    margin: float
    lenient: bool
    spot_check: float
    min_runs: int
    min_good: int
    # autorate.metrics keys with no rated metric of that name, so they set nothing
    unused: tuple = ()

    def of(self, key):
        return self.metrics.get(key, NO_POLICY)


def worse_direction(rules):
    """+1 where higher values are worse, -1 where lower ones are, None where the rules do not say."""
    ops = [(tier, op) for tier, (op, _) in rules.items()]
    if any((t == "bad" and op in UPWARD) or (t == "good" and op in DOWNWARD) for t, op in ops):
        return 1
    if any((t == "bad" and op in DOWNWARD) or (t == "good" and op in UPWARD) for t, op in ops):
        return -1
    return None


def default_block():
    with open(default_config_path("afni"), encoding="utf-8") as f:
        return json.load(f)["autorate"]


def parse_policy(block, metrics, source="config"):
    """Check the autorate block against the config's metrics; raises ConfigError naming the field."""
    where = f"{source}: autorate"
    if not isinstance(block, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = sorted(set(block) - set(_FIELDS))
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {unknown}; allowed: {', '.join(_FIELDS)}")
    missing = [f for f in _FIELDS if f not in block]
    if missing:
        raise ConfigError(f"{where}: missing {', '.join(missing)}; 'fmriqc config afni' writes a complete block")

    rated = {key: m for key, m in metrics.items() if m.rated}
    entries = _object(block["metrics"], f"{where}.metrics")
    policies, unused = {}, []
    for key, entry in entries.items():
        if key not in rated:
            unused.append(key)
            continue
        policies[key] = _parse_metric_policy(entry, rated[key], f"{where}.metrics.{key}")

    mot = block["mot"]
    if not isinstance(mot, str) or mot not in rated:
        raise ConfigError(f"{where}.mot must name a metric with thresholds under metrics, such as \"cens_frac\"")
    if worse_direction(rated[mot].rules) is None:
        raise ConfigError(f"{where}.mot: {mot} needs a threshold with <, <=, > or >=")

    warns = dict(_object(block["warns"], f"{where}.warns"))
    column = warns.pop("metric", None)
    if not isinstance(column, str) or not column:
        raise ConfigError(f"{where}.warns.metric must name a column, such as \"cens_frac\"")
    try:
        warns_metric = parse_entry(column, warns)
    except ConfigError as e:
        raise ConfigError(f"{where}.warns: {e}") from None

    weights = _object(block["weights"], f"{where}.weights")
    for section, weight in weights.items():
        if section not in NUMERIC_SECTIONS + RATED_SECTIONS:
            raise ConfigError(f"{where}.weights: {section!r} is not an APQC section; "
                              f"use {', '.join(NUMERIC_SECTIONS + RATED_SECTIONS)}")
        _number(weight, f"{where}.weights.{section}")

    veto_sections = block["veto_sections"]
    if not isinstance(veto_sections, list) or not all(s in NUMERIC_SECTIONS for s in veto_sections):
        raise ConfigError(f"{where}.veto_sections must list sections the numbers settle "
                          f"({', '.join(NUMERIC_SECTIONS)}), such as [\"mot\"]")

    cutoffs = _object(block["cutoffs"], f"{where}.cutoffs")
    if set(cutoffs) != {"bad", "other"}:
        raise ConfigError(f"{where}.cutoffs must have exactly bad and other, such as {{\"bad\": 10.5, \"other\": 5}}")
    cut_bad = _number(cutoffs["bad"], f"{where}.cutoffs.bad", minimum=None)
    cut_other = _number(cutoffs["other"], f"{where}.cutoffs.other", minimum=None)
    if not cut_other < cut_bad:
        raise ConfigError(f"{where}.cutoffs: other ({cut_other:g}) must be below bad ({cut_bad:g})")

    spot_check = _number(block["spot_check"], f"{where}.spot_check")
    if spot_check > 1:
        raise ConfigError(f"{where}.spot_check is a share of runs, from 0 to 1, such as 0.1")
    if not isinstance(block["lenient"], bool):
        raise ConfigError(f"{where}.lenient must be true or false")

    calibration = _object(block["calibration"], f"{where}.calibration")
    if set(calibration) != {"min_runs", "min_good"}:
        raise ConfigError(f"{where}.calibration must have exactly min_runs and min_good")
    min_runs = _count(calibration["min_runs"], f"{where}.calibration.min_runs", minimum=1)
    min_good = _count(calibration["min_good"], f"{where}.calibration.min_good", minimum=0)

    return Policy(metrics=policies, mot=mot, warns_column=column, warns=warns_metric,
                  weights={s: float(w) for s, w in weights.items()}, veto_sections=tuple(veto_sections),
                  cut_bad=cut_bad, cut_other=cut_other, margin=_number(block["margin"], f"{where}.margin"),
                  lenient=block["lenient"], spot_check=spot_check, min_runs=min_runs, min_good=min_good,
                  unused=tuple(unused))


def _parse_metric_policy(entry, metric, where):
    entry = _object(entry, where)
    unknown = sorted(set(entry) - set(_METRIC_FIELDS))
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {unknown}; allowed: {', '.join(_METRIC_FIELDS)}")
    veto = entry.get("veto", False)
    if not isinstance(veto, bool):
        raise ConfigError(f"{where}.veto must be true or false")
    tolerance = _parse_tolerance(entry.get("tolerance", 0), f"{where}.tolerance")
    if tolerance.amount and worse_direction(metric.rules) is None:
        raise ConfigError(f"{where}.tolerance needs a threshold with <, <=, > or >=")
    return MetricPolicy(tolerance, veto)


def _parse_tolerance(value, where):
    """0.1 is 0.1 in the metric's units; "10%" is a tenth of the line the value crossed."""
    if isinstance(value, str):
        match = _PERCENT.fullmatch(value)
        if match is None:
            raise ConfigError(f"{where} must be a number such as 0.1, or a percentage such as \"10%\"")
        return Tolerance(float(match.group(1)) / 100, relative=True)
    return Tolerance(_number(value, where))


def _object(value, where):
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be an object")
    return value


def _number(value, where, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (minimum is not None and value < minimum):
        raise ConfigError(f"{where} must be a number" + ("" if minimum is None else f" of at least {minimum}"))
    return float(value)


def _count(value, where, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{where} must be a whole number of at least {minimum}")
    return value
