"""
fmriqc autorate afni: rate AFNI runs with the lab's policy, optionally after choosing the score cutoffs
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ..dashboard.config import backup_path, config_to_raw, default_config_path, load_config, save_config
from .calibrate import calibrate
from .policy import NUMERIC_SECTIONS, default_block, parse_policy
from .rate import CODE, EXCLUDE, INCLUDE, PERSON, decide, mark_checks

TABLE_FILE = "autorate.csv"
SUMMARY_FILE = "autorate_summary.txt"


class CalibrationError(ValueError):
    pass


def load(config_path):
    """(config, policy, file read, notes): from the config file, or the package's default when there is none."""
    path = Path(config_path) if config_path and Path(config_path).exists() else default_config_path("afni")
    config = load_config(path)
    notes = []
    block = config.autorate
    if block is None:
        block = default_block()
        notes.append(f"{path} has no autorate settings, so the package's defaults were used with its thresholds.")
    policy = parse_policy(block, config.metrics, source=str(path))
    if policy.unused:
        notes.append(f"autorate.metrics lists {', '.join(policy.unused)}, which has no thresholds under metrics, "
                     f"so it is not used.")
    return config, policy, path, notes


def calibration_runs(df, S, policy):
    """Runs with a FINAL rating and every weighted section known: the ones the cutoffs are chosen on."""
    if "FINAL_rating" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["FINAL_rating"].isin(list(CODE)) & S[list(policy.weights)].notna().all(axis=1)


def calibrate_config(df, config, policy, save_path):
    """Choose the cutoffs on the rated runs and save them to the config; returns the report lines."""
    _, S, score, veto = decide(df, config, policy)
    use = calibration_runs(df, S, policy)
    y = df.loc[use, "FINAL_rating"].map(CODE)
    counts = {level: int((y == code).sum()) for level, code in CODE.items()}
    problems = []
    if use.sum() < policy.min_runs:
        problems.append(f"{int(use.sum())} runs have a FINAL rating and a rating for every weighted image section; "
                        f"at least {policy.min_runs} are needed")
    if counts["good"] < policy.min_good:
        problems.append(f"{counts['good']} of them are rated good; at least {policy.min_good} are needed")
    if counts["bad"] == 0:
        problems.append("none of them is rated bad, so the bad cutoff cannot be placed")
    if problems:
        raise CalibrationError("; ".join(problems) + ". Rate more runs in APQC (fmriqc rating afni), or change "
                               "autorate.calibration in the config.")

    groups = df.loc[use, "ID"].astype(str)
    result = calibrate(y.to_numpy(), score[use].to_numpy(), veto[use].to_numpy(), groups.to_numpy(),
                       (policy.cut_bad, policy.cut_other))
    raw = config_to_raw(config)
    block = dict(config.autorate if config.autorate is not None else default_block())
    block["cutoffs"] = {"bad": result.cut_bad, "other": result.cut_other}
    raw["autorate"] = block
    existed = Path(save_path).exists()
    save_config(save_path, raw)
    return [
        f"Calibrated on {int(use.sum())} runs rated in APQC (good {counts['good']}, other {counts['other']}, "
        f"bad {counts['bad']}).",
        f"  Cutoffs: bad {result.cut_bad:g}, other {result.cut_other:g} "
        f"(before: bad {policy.cut_bad:g}, other {policy.cut_other:g}).",
        f"  Agreement with the rater's FINAL on these runs: kappa {result.kappa:.2f}, accuracy {result.accuracy:.2f}.",
        f"  With each participant's cutoffs chosen on the other participants: kappa {result.loo_kappa:.2f}, "
        f"accuracy {result.loo_accuracy:.2f}. This is the better guide to runs that are not rated.",
        f"  Saved to {save_path}" + (f" (the file before is kept as {backup_path(save_path).name})." if existed
                                     else "."),
    ]


def rate(df, config, policy):
    """The output table: ID columns, decision, check, reason, FINAL and the rater's FINAL, then the detail."""
    table, S, _, _ = decide(df, config, policy)
    ids = df[[c for c in ("ID", "session") if c in df.columns]]
    rater = df["FINAL_rating"].where(df["FINAL_rating"].isin(list(CODE))) if "FINAL_rating" in df.columns else None
    out = pd.concat([ids, table[["decision"]]], axis=1)
    out["check"] = mark_checks(table["decision"], policy.spot_check)
    out["reason"] = table["reason"]
    out["FINAL"] = table["FINAL"]
    out["rater_FINAL"] = rater if rater is not None else np.nan
    return pd.concat([out, table.drop(columns=["decision", "reason", "FINAL"])], axis=1)


def summary(out, policy, path, notes):
    n = len(out)
    lines = [f"Rated {n} runs with {path} (cutoffs: bad {policy.cut_bad:g}, other {policy.cut_other:g}; "
             f"margin {policy.margin:g})."]
    for group in (INCLUDE, EXCLUDE, PERSON):
        members = out["decision"] == group
        checks = int((members & (out["check"] == "yes")).sum())
        lines.append(f"  {group:<8}{int(members.sum()):>6} ({members.mean():.0%})"
                     + (f", {checks} marked in the check column" if group != PERSON else ""))
    lines.append(f"A person looks at {int(((out['decision'] == PERSON) | (out['check'] == 'yes')).sum())} runs: "
                 f"the person group and the marked checks.")
    rated = out["rater_FINAL"].notna()
    if rated.any():
        both = rated & out["FINAL"].notna()
        agree = (out.loc[both, "FINAL"] == out.loc[both, "rater_FINAL"]).mean() if both.any() else float("nan")
        lines.append(f"{int(rated.sum())} runs have a FINAL rating from APQC; the policy's FINAL matches it on "
                     f"{agree:.0%} of the {int(both.sum())} where the policy gives one.")
        lines.append(pd.crosstab(out.loc[both, "rater_FINAL"].rename("rater"), out.loc[both, "FINAL"].rename("policy"))
                     .reindex(index=list(CODE), columns=list(CODE), fill_value=0).to_string())
    missing = [s for s in policy.weights if s not in NUMERIC_SECTIONS and out[f"{s}_rating"].isna().all()]
    if missing:
        notes = notes + [f"No run has a rating for {', '.join(missing)}, so no run can be included automatically."]
    return "\n".join(lines + [f"Note: {note}" for note in notes])


def run(df, config_path, output_dir, do_calibrate=False):
    """Rate the runs in df, write the table and the summary to output_dir, and return the summary text."""
    config, policy, path, notes = load(config_path)
    lines = []
    if do_calibrate:
        lines += calibrate_config(df, config, policy, config_path)
        config, policy, path, notes = load(config_path)
    out = rate(df, config, policy)
    output_dir = Path(output_dir)
    out.to_csv(output_dir / TABLE_FILE, index=False)
    text = "\n".join(lines + [summary(out, policy, path, notes)])
    (output_dir / SUMMARY_FILE).write_text(text + "\n", encoding="utf-8")
    return text
