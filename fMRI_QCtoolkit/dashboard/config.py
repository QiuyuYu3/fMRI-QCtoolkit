"""
Dashboard config: which metrics the sidebar shows and the thresholds that set their status
"""

import json
import os
import shutil
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path

from ..utils.status import DOWNWARD, UPWARD, format_rule, parse_rule

CONFIG_FILES = {"afni": "afni_config.json", "fmriprep": "fmriprep_config.json"}
# Columns of df_final.csv that identify a run rather than measure it
ID_COLUMNS = ("ID", "session", "run")
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


def config_beside(data_file, pipeline):
    """The config a dashboard uses without --config: the pipeline's config file name in the data file's folder."""
    return Path(data_file).parent / CONFIG_FILES[pipeline]


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


def parse_entry(key, entry):
    """One metric entry, checked as parse_config checks it."""
    return _parse_metric(key, entry, f"metrics.{key}")


def config_to_raw(config):
    metrics = {}
    for key, metric in config.items():
        entry = {"label": metric.entry_label}
        entry.update({tier: format_rule(metric.rules[tier]) for tier in ("other", "bad") if tier in metric.rules})
        if metric.step is not None:
            entry["step"] = metric.step
        metrics[key] = entry
    return {"metrics": metrics}


def dump_config(raw):
    """JSON text with one line per metric and each field in its own column, as the default files are laid out."""
    rows = []
    for key, entry in raw["metrics"].items():
        fields = {f: f"{json.dumps(f)}: {json.dumps(entry[f], ensure_ascii=False)}"
                  for f in _METRIC_FIELDS if f in entry}
        rows.append((json.dumps(key, ensure_ascii=False) + ":", fields))
    key_width = max((len(key) for key, _ in rows), default=0) + 1
    widths = {f: max((len(fields[f]) + 2 for _, fields in rows if f in fields), default=0) for f in _METRIC_FIELDS}
    lines = []
    for key, fields in rows:
        present = [f for f in _METRIC_FIELDS if f in fields]
        cells = [(fields[f] + "," if f in fields else "").ljust(widths[f])
                 for f in _METRIC_FIELDS[:_METRIC_FIELDS.index(present[-1])]] if present else []
        cells += [fields[present[-1]]] if present else []
        lines.append(f"    {key.ljust(key_width)}{{{''.join(cells)}}}")
    return '{\n  "metrics": {\n' + ",\n".join(lines) + "\n  }\n}\n"


def save_config(path, raw):
    """Check `raw` and write it over `path` in one step; the file it replaces is kept as <name>.bak."""
    path = Path(path)
    config = parse_config(raw, source=str(path))
    text = dump_config(raw)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copyfile(path, backup_path(path))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return config


def backup_path(path):
    path = Path(path)
    return path.with_name(path.name + ".bak")


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
