"""
Rate runs from their numbers and the lab's policy, then sort them into include, exclude and a person's review
"""

import math

import numpy as np
import pandas as pd

from ..dashboard.config import ID_COLUMNS, resolve_metrics
from ..utils.status import assign_status, rest_tier
from .policy import NUMERIC_SECTIONS, worse_direction

CODE = {"good": 0, "other": 1, "bad": 2}
LEVEL = {code: level for level, code in CODE.items()}
# Columns the APQC rating buttons fill; they must never reach the numbers
RATER_SUFFIXES = ("_rating", "_comment")
INCLUDE, EXCLUDE, PERSON = "include", "exclude", "person"


def metric_columns(config, columns):
    """{config key: matching columns} for the rated metrics, leaving out ID, rating and comment columns."""
    usable = [c for c in columns if c not in ID_COLUMNS and not c.endswith(RATER_SUFFIXES)]
    groups = {}
    for metric in resolve_metrics(config.metrics, usable):
        if metric.rated:
            groups.setdefault(metric.entry, []).append(metric.column)
    return groups


def _codes(values, metric):
    return assign_status(values, metric.rules, metric.otherwise).map(CODE).astype(float)


def _crossed_line(metric, code):
    """The threshold a value at this level is past, coming from the better side; None if there is none."""
    rules, rest = metric.rules, rest_tier(metric.rules, metric.otherwise)
    if code == 2:
        if rest == "bad" and "good" in rules:
            return rules["good"][1]
        return rules["bad"][1] if "bad" in rules else None
    if code == 1 and rest == "other" and "good" in rules:
        return rules["good"][1]
    return None


def shifted_codes(values, metric, tolerance, k):
    """Levels of the values moved k tolerances toward the better side of the line each one crossed."""
    level = _codes(values, metric)
    if k == 0 or tolerance.amount == 0:
        return level
    if tolerance.relative:
        lines = level.map(lambda code: _crossed_line(metric, code)).astype(float)
        step = (tolerance.amount * lines.abs()).fillna(0.0)
    else:
        step = tolerance.amount
    # Rounded so that a value exactly k tolerances past a line counts as past it
    moved = (values - worse_direction(metric.rules) * k * step).round(10)
    return _codes(moved, metric)


def metric_levels(df, config, policy):
    """Per metric key, each run's level (L0) and its level moved back one (L1) and two (L2) tolerances."""
    levels = ({}, {}, {})
    # A key that matches several columns takes the worst of them
    for key, columns in metric_columns(config, df.columns).items():
        metric, tolerance = config.metrics[key], policy.of(key).tolerance
        for k in range(3):
            per_column = [shifted_codes(pd.to_numeric(df[c], errors="coerce"), metric, tolerance, k) for c in columns]
            levels[k][key] = pd.concat(per_column, axis=1).max(axis=1)
    return tuple(pd.DataFrame(level, index=df.index) for level in levels)


def qsumm_codes(L0, L1, policy):
    """Each run's qsumm under the lab policy; NaN where no metric has a value."""
    border = L1 < L0
    veto = [key for key in L0 if policy.of(key).veto]
    clear = ((L0[veto] == 2) & (L1[veto] == 2)).any(axis=1)
    out = pd.Series(np.nan, index=L0.index)
    for i in L0.index:
        known = L0.loc[i].dropna()
        # A veto metric past its bad line by more than the tolerance
        if clear[i]:
            out[i] = 2
            continue
        if known.empty:
            continue
        effective = []
        for key, code in known.items():
            rest_good = bool((known.drop(key) == 0).all())
            # Within the tolerance: one level better if the rest is good, or always when lenient
            if code > 0 and border.at[i, key] and (rest_good or policy.lenient):
                effective.append(code - 1)
            # A clear failure of a metric that cannot veto is only other while the rest is good
            elif code == 2 and not border.at[i, key] and rest_good:
                effective.append(1)
            else:
                effective.append(code)
        out[i] = max(effective)
    return out


def rated_sections(df, names):
    """Levels of the image sections, as codes with NaN where there is none; for now the rater's APQC ratings."""
    return pd.DataFrame({s: df[f"{s}_rating"].map(CODE).astype(float) if f"{s}_rating" in df.columns else np.nan
                         for s in names}, index=df.index)


def sections(df, config, policy, L0, L1):
    """Section levels as codes: qsumm, mot and warns from the numbers, every other section from rated_sections."""
    wanted = list(dict.fromkeys([*policy.weights, *policy.veto_sections]))
    out = rated_sections(df, [s for s in wanted if s not in NUMERIC_SECTIONS])
    for section in wanted:
        if section == "qsumm":
            out[section] = qsumm_codes(L0, L1, policy)
        elif section == "mot":
            out[section] = L1[policy.mot] if policy.mot in L1 else np.nan
        elif section == "warns":
            column = policy.warns_column
            out[section] = (_codes(pd.to_numeric(df[column], errors="coerce"), policy.warns)
                            if column in df.columns else np.nan)
    return out[wanted]


def veto_zones(L0, L1, L2, policy):
    """Per run, the veto metrics past their bad line by more than one tolerance (clear) and by two or more (hard)."""
    veto = [key for key in L0 if policy.of(key).veto]
    clear = (L0[veto] == 2) & (L1[veto] == 2)
    hard = L2[veto] == 2
    return clear, hard


def scores(S, policy):
    """The weighted score with unrated sections counted good (low) and bad (high); equal when all are rated."""
    weights = pd.Series(policy.weights)
    weighted = S[list(weights.index)]
    return (weighted.fillna(0) * weights).sum(axis=1), (weighted.fillna(2) * weights).sum(axis=1)


def final_codes(low, high, veto, cut_bad, cut_other):
    """The policy's FINAL: bad on a veto, else by the score cutoffs; NaN where unrated sections leave it open."""
    final = np.where(low >= cut_bad, 2, np.where(high < cut_other, 0,
                     np.where((low >= cut_other) & (high < cut_bad), 1, np.nan)))
    return pd.Series(np.where(veto, 2, final), index=low.index)


def decide(df, config, policy):
    """One row per run: the decision, why, the policy's FINAL, the score and the section levels."""
    L0, L1, L2 = metric_levels(df, config, policy)
    S = sections(df, config, policy, L0, L1)
    low, high = scores(S, policy)
    clear, hard = veto_zones(L0, L1, L2, policy)
    section_veto = (S[list(policy.veto_sections)] == 2) if policy.veto_sections else pd.DataFrame(index=df.index)
    veto = clear.any(axis=1) | section_veto.any(axis=1)
    # Just past the tolerance on some metric, and well past it on none
    soft = clear.where(~hard.any(axis=1), False, axis=0)
    rated = [s for s in policy.weights if s not in NUMERIC_SECTIONS]
    numeric = [s for s in policy.weights if s in NUMERIC_SECTIONS]
    known = S[list(policy.weights)].notna().all(axis=1)
    cut, margin = policy.cut_bad, policy.margin

    decisions, reasons = [], []
    for i in df.index:
        rated_bad = [s for s in rated if S.at[i, s] == 2]
        numbers_bad = any(S.at[i, s] == 2 for s in numeric)
        if veto[i]:
            soft_keys = [key for key in soft.columns if soft.at[i, key]]
            if soft_keys and low[i] < cut:
                decisions.append(PERSON)
                reasons.append(f"{', '.join(soft_keys)} just past the tolerance, but the score is below the bad "
                               f"cutoff {_num(cut)}")
            else:
                triggers = [f"{key} past its bad line" for key in clear.columns if clear.at[i, key]]
                triggers += [f"{s} bad" for s in section_veto.columns if section_veto.at[i, s]]
                decisions.append(EXCLUDE)
                reasons.append("veto: " + "; ".join(triggers))
        elif rated_bad and not numbers_bad:
            decisions.append(PERSON)
            reasons.append(f"{', '.join(rated_bad)} rated bad while the numbers are not bad")
        elif low[i] >= cut + margin:
            decisions.append(EXCLUDE)
            reasons.append(f"score {_num(low[i])} at or above {_num(cut + margin)}")
        elif not known[i]:
            decisions.append(PERSON)
            reasons.append("not rated: " + ", ".join(s for s in policy.weights if pd.isna(S.at[i, s])))
        elif rated_bad:
            decisions.append(PERSON)
            reasons.append(f"{', '.join(rated_bad)} rated bad")
        elif high[i] < cut - margin:
            decisions.append(INCLUDE)
            reasons.append(f"score {_num(high[i])} below {_num(cut - margin)}")
        else:
            decisions.append(PERSON)
            reasons.append(f"score {_num(low[i])} within {_num(margin)} of the bad cutoff {_num(cut)}")

    final = final_codes(low, high, veto, cut, policy.cut_other)
    return pd.DataFrame({
        "decision": decisions,
        "reason": reasons,
        "FINAL": final.map(LEVEL),
        "score": low.where(known),
        "thresholds": L0.max(axis=1).map(LEVEL),
        **{s: S[s].map(LEVEL) for s in S.columns if s in NUMERIC_SECTIONS},
        **{f"{s}_rating": S[s].map(LEVEL) for s in S.columns if s not in NUMERIC_SECTIONS},
        "flagged": _flagged(L0, L1),
    }, index=df.index), S, low, veto


def _flagged(L0, L1):
    """The metrics that are not good, with their level and whether they are within the tolerance."""
    out = []
    for i in L0.index:
        items = [f"{key} {LEVEL[code]}" + (" (within tolerance)" if L1.at[i, key] < code else "")
                 for key, code in L0.loc[i].items() if code > 0]
        out.append("; ".join(items))
    return pd.Series(out, index=L0.index)


def mark_checks(decisions, share, seed=0):
    """A share of each automatic group, drawn at random, for a person to check."""
    rng = np.random.default_rng(seed)
    check = pd.Series("", index=decisions.index)
    for group in (INCLUDE, EXCLUDE):
        members = decisions.index[decisions == group]
        n = math.ceil(share * len(members))
        if n:
            check[rng.choice(members, size=n, replace=False)] = "yes"
    return check


def _num(value):
    return f"{value:g}"
