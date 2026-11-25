"""
Dashboard config: which metrics the sidebar shows and the thresholds that set their status
"""

import json
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path

from ..utils.status import DOWNWARD, UPWARD, format_rule, parse_rule

CONFIG_FILES = {"afni": "afni_config.json", "fmriprep": "fmriprep_config.json"}
_METRIC_FIELDS = ("label", "other", "bad", "step")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Metric:
    column: str
    label: str
    rules: dict
    step: float = None
    entry: str = ""
    entry_label: str = ""


def default_config_path(pipeline):
    return Path(__file__).with_name(CONFIG_FILES[pipeline])


def load_config(path):
    """Read and check a dashboard config; returns {config key: Metric}."""
    path = Path(path)
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: not valid JSON ({e})") from None
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from None
    return parse_config(raw, source=str(path))


def parse_config(raw, source="config"):
    if not isinstance(raw, dict) or "metrics" not in raw:
        old = isinstance(raw, dict) and "quantitative_configs" in raw
        hint = " This is the 1.x format; get the current one with 'fmriqc config'." if old else ""
        raise ConfigError(f"{source}: expected an object with a 'metrics' entry.{hint}")
    unknown = sorted(set(raw) - {"metrics"})
    if unknown:
        raise ConfigError(f"{source}: unknown top-level field(s) {unknown}; only 'metrics' is allowed")
    metrics = raw["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise ConfigError(f"{source}: 'metrics' must be a non-empty object keyed by df_final.csv column")
    return {key: _parse_metric(key, entry, f"{source}: metrics.{key}") for key, entry in metrics.items()}


def resolve_metrics(config, columns):
    """Config entries matched to the table's columns, in config order; a '*' key expands to every matching column."""
    resolved, seen = [], set()
    for key, metric in config.items():
        pattern = "*" in key
        if pattern:
            matches = [c for c in columns if fnmatchcase(c, key)]
        else:
            matches = [key] if key in columns else []
        for column in matches:
            if column not in seen:
                seen.add(column)
                resolved.append(replace(metric, column=column, label=column if pattern else metric.label))
    return resolved


def _reject_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ConfigError(f"duplicate key(s) {duplicates}")
    return dict(pairs)


def _parse_metric(key, entry, where):
    if not isinstance(entry, dict):
        raise ConfigError(f"{where} must be an object, such as {{\"label\": \"GCOR\", \"bad\": \">= 0.2\"}}")
    unknown = sorted(set(entry) - set(_METRIC_FIELDS))
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {unknown}; allowed: {', '.join(_METRIC_FIELDS)}")
    label = entry.get("label", key)
    if not isinstance(label, str):
        raise ConfigError(f"{where}.label must be text")
    step = entry.get("step")
    if step is not None and (isinstance(step, bool) or not isinstance(step, (int, float)) or step <= 0):
        raise ConfigError(f"{where}.step must be a positive number")
    rules = {}
    for tier in ("other", "bad"):
        if tier in entry:
            try:
                rules[tier] = parse_rule(entry[tier])
            except ValueError as e:
                raise ConfigError(f"{where}.{tier}: {e}") from None
    _check_order(rules, where)
    return Metric(column=key, label=label, rules=rules, step=step, entry=key, entry_label=label)


def _check_order(rules, where):
    if len(rules) < 2:
        return
    (other_op, other_value), (bad_op, bad_value) = rules["other"], rules["bad"]
    shown = f"other ({format_rule(rules['other'])}) and bad ({format_rule(rules['bad'])})"
    for direction in (UPWARD, DOWNWARD):
        if other_op in direction and bad_op in direction:
            looser = bad_value < other_value if direction is UPWARD else bad_value > other_value
            if looser:
                raise ConfigError(f"{where}: bad is looser than other, so nothing can be 'other' "
                                  f"({shown}); are they swapped?")
            return
    if {other_op, bad_op} <= UPWARD | DOWNWARD:
        raise ConfigError(f"{where}: {shown} point in opposite directions")
