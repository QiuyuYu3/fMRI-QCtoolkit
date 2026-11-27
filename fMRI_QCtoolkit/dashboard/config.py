"""
Dashboard config: which metrics the sidebar shows and the thresholds that set their status
"""

import json
import os
import shutil
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path

from ..utils.status import (LEVELS, RULE_TIERS, format_number, format_rule, negate_rule, overlap, parse_rule,
                            rest_tier)

CONFIG_FILES = {"afni": "afni_config.json", "fmriprep": "fmriprep_config.json", "custom": "custom_config.json"}
# Columns of df_final.csv that identify a run rather than measure it
ID_COLUMNS = ("ID", "session", "run")
_METRIC_FIELDS = ("label", *RULE_TIERS, "otherwise", "step")
_TOP_FIELDS = ("metrics", "table_columns")


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
    # The level of a value that meets neither rule, when the config sets one
    otherwise: str = None

    @property
    def rated(self):
        return bool(self.rules) or self.otherwise is not None


@dataclass(frozen=True, eq=False)
class Config:
    """{config key: Metric}, and the columns the table shows after the metrics, without a filter or rating."""
    metrics: dict
    table_columns: tuple = ()

    def __eq__(self, other):
        # Metric order counts: it is the order of the sidebar and the table
        if not isinstance(other, Config):
            return NotImplemented
        return (list(self.metrics.items()), self.table_columns) == (list(other.metrics.items()), other.table_columns)


def same_settings(a, b):
    """Whether two configs set the same; metric order counts, while table-only columns always show in data order."""
    return list(a.metrics.items()) == list(b.metrics.items()) and set(a.table_columns) == set(b.table_columns)


def default_config_path(pipeline):
    return Path(__file__).with_name(CONFIG_FILES[pipeline])


def config_beside(data_file, pipeline):
    """The config a dashboard uses without --config: the pipeline's config file name in the data file's folder."""
    return Path(data_file).parent / CONFIG_FILES[pipeline]


def load_config(path):
    """Read and check a dashboard config file."""
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
    unknown = sorted(set(raw) - set(_TOP_FIELDS))
    if unknown:
        raise ConfigError(f"{source}: unknown top-level field(s) {unknown}; allowed: {', '.join(_TOP_FIELDS)}")
    metrics = raw["metrics"]
    if not isinstance(metrics, dict):
        raise ConfigError(f"{source}: 'metrics' must be an object keyed by df_final.csv column")
    metrics = {key: _parse_metric(key, entry, f"{source}: metrics.{key}") for key, entry in metrics.items()}
    return Config(metrics, parse_table_columns(raw.get("table_columns", []), metrics, f"{source}: table_columns"))


def parse_entry(key, entry):
    """One metric entry, checked as parse_config checks it."""
    return _parse_metric(key, entry, f"metrics.{key}")


def parse_table_columns(columns, metric_keys, where="table_columns"):
    """The table-only columns, checked as parse_config checks them."""
    if not isinstance(columns, list) or not all(isinstance(c, str) and c for c in columns):
        raise ConfigError(f"{where} must be a list of df_final.csv column names")
    repeated = sorted({c for c in columns if columns.count(c) > 1})
    if repeated:
        raise ConfigError(f"{where}: {repeated} listed more than once")
    in_metrics = [c for c in columns if c in metric_keys]
    if in_metrics:
        raise ConfigError(f"{where}: {in_metrics} already in metrics; list each column in one place")
    return tuple(columns)


def config_to_raw(config):
    metrics = {}
    for key, metric in config.metrics.items():
        entry = {"label": metric.entry_label}
        entry.update({tier: format_rule(metric.rules[tier]) for tier in RULE_TIERS if tier in metric.rules})
        if metric.otherwise is not None:
            entry["otherwise"] = metric.otherwise
        if metric.step is not None:
            entry["step"] = metric.step
        metrics[key] = entry
    raw = {"metrics": metrics}
    if config.table_columns:
        raw["table_columns"] = list(config.table_columns)
    return raw


def dump_config(raw):
    """JSON text with one line per metric, each field in its own column, as the default files are laid out."""
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
    text = '{\n  "metrics": {\n' + ",\n".join(lines) + "\n  }" if lines else '{\n  "metrics": {}'
    if raw.get("table_columns"):
        text += ',\n  "table_columns": ' + json.dumps(list(raw["table_columns"]), ensure_ascii=False)
    return text + "\n}\n"


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


def resolve_metrics(metrics, columns):
    """Config entries matched to the table's columns, in config order; a '*' key expands to every matching column."""
    resolved, seen = [], set()
    for key, metric in metrics.items():
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
    if "other" in entry:
        try:
            good = format_rule(negate_rule(parse_rule(entry["other"])))
            hint = f'; replace "other": "{entry["other"]}" with "good": "{good}"'
        except ValueError:
            hint = ""
        raise ConfigError(f"{where}: 'other' is no longer a field, since other is whatever is neither good nor "
                          f"bad{hint}")
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
    for tier in RULE_TIERS:
        if tier in entry:
            try:
                rules[tier] = parse_rule(entry[tier])
            except ValueError as e:
                raise ConfigError(f"{where}.{tier}: {e}") from None
    if len(rules) == 2:
        both = overlap(rules["good"], rules["bad"])
        if both is not None:
            raise ConfigError(f"{where}: good ({format_rule(rules['good'])}) and bad ({format_rule(rules['bad'])}) "
                              f"overlap, so a value such as {format_number(both)} would be both")
    otherwise = entry.get("otherwise")
    if otherwise is not None and otherwise not in LEVELS:
        raise ConfigError(f"{where}.otherwise must be one of {', '.join(LEVELS)}")
    # Read as the Settings tab writes entries, so an untouched form shows no unsaved changes
    label = label.strip() or key
    otherwise = None if otherwise == rest_tier(rules) else otherwise
    return Metric(column=key, label=label, rules=rules, step=step, entry=key, entry_label=label, otherwise=otherwise)
