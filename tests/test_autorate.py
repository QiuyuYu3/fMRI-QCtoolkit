import json
import re

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from fMRI_QCtoolkit import cli
from fMRI_QCtoolkit.autorate.afni import CalibrationError, calibrate_config, load, rate
from fMRI_QCtoolkit.autorate.calibrate import choose, kappa_accuracy
from fMRI_QCtoolkit.autorate.policy import default_block, parse_policy
from fMRI_QCtoolkit.autorate.rate import decide, mark_checks, metric_columns
from fMRI_QCtoolkit.dashboard.config import ConfigError, default_config_path, load_config, parse_config

RATED = ("vorig", "ve2a", "va2t", "vstat", "regr", "radcor")
CLEAN = {"cens_frac": 0.05, "cens_mot": 0.05, "cens_displace": 1.0, "TSNR": 200.0, "DF_frac": 0.9,
         "flip_guess": 0, "GCOR": 0.05, "frac_TRs_cens_1": 0.05}
runner = CliRunner()


def runs(*changes):
    """One run per dict of changes to a clean run whose image sections are all rated good."""
    rows = [{"ID": f"{i + 1:02d}", **CLEAN, **{f"{s}_rating": "good" for s in RATED}, **change}
            for i, change in enumerate(changes)]
    return pd.DataFrame(rows)


def default(**block_changes):
    config = load_config(default_config_path("afni"))
    block = {**config.autorate, **block_changes}
    return config, parse_policy(block, config.metrics)


def rated(*changes, **block_changes):
    config, policy = default(**block_changes)
    return decide(runs(*changes), config, policy)[0]


class TestSectionsFromNumbers:

    def test_a_value_within_the_tolerance_counts_one_level_better_when_the_rest_is_good(self):
        table = rated({"cens_frac": 0.25})
        assert table.loc[0, ["thresholds", "qsumm", "mot", "warns"]].tolist() == ["bad", "other", "other", "other"]
        assert table.loc[0, "flagged"] == "cens_frac bad (within tolerance)"

    def test_it_does_not_when_another_metric_is_not_good_unless_lenient(self):
        assert rated({"cens_frac": 0.25, "GCOR": 0.16}).loc[0, "qsumm"] == "bad"
        assert rated({"cens_frac": 0.25, "GCOR": 0.16}, lenient=True).loc[0, "qsumm"] == "other"

    def test_a_clear_failure_of_a_metric_that_cannot_veto_is_other_when_the_rest_is_good(self):
        table = rated({"GCOR": 0.3}, {"GCOR": 0.3, "cens_frac": 0.16})
        assert table.qsumm.tolist() == ["other", "bad"]
        assert table.decision.tolist() == ["include", "include"]

    def test_mot_moves_the_censor_fraction_back_by_the_tolerance(self):
        table = rated(*({"cens_frac": c} for c in (0.22, 0.27, 0.3, 0.31)))
        assert table.mot.tolist() == ["good", "other", "bad", "bad"]

    def test_warns_follows_its_own_censor_lines(self):
        assert rated(*({"cens_frac": c} for c in (0.19, 0.2, 0.5))).warns.tolist() == ["good", "other", "bad"]

    def test_a_metric_named_with_a_star_takes_its_worst_column(self):
        table = rated({"frac_TRs_cens_1": 0.1, "frac_TRs_cens_2": 0.45})
        assert table.loc[0, "decision"] == "exclude"
        assert "frac_TRs_cens_* past its bad line" in table.loc[0, "reason"]


class TestRatingsStayOutOfTheNumbers:

    def test_rating_and_comment_columns_never_match_a_metric(self):
        config = parse_config({"metrics": {"*": {"bad": ">= 0.5"}}})
        columns = ["ID", "session", "cens_frac", "vstat_rating", "FINAL_rating", "qsumm_rating", "vstat_comment"]
        assert metric_columns(config, columns) == {"*": ["cens_frac"]}

    def test_changing_the_ratings_leaves_the_sections_from_numbers_alone(self):
        config, policy = default()
        df = runs({"cens_frac": 0.25}, {"GCOR": 0.3})
        flipped = df.assign(qsumm_rating="bad", mot_rating="bad", warns_rating="bad", FINAL_rating="bad",
                            vstat_comment=0.9)
        columns = ["thresholds", "qsumm", "mot", "warns", "flagged"]
        assert decide(df, config, policy)[0][columns].equals(decide(flipped, config, policy)[0][columns])

    def test_from_the_json_files_too(self, tmp_path):
        info = tmp_path / "rest_output" / "QC_sub-01" / "extra_info"
        info.mkdir(parents=True)
        (info / "out.ss_review.sub-01.json").write_text(json.dumps({
            "censor fraction": "0.25", "global correlation (GCOR)": "0.05", "flip guess": "NO_FLIP",
            "qsumm rating": "bad", "FINAL rating": "bad", "FINAL comment": "0.9"}))
        result = runner.invoke(cli.app, ["autorate", "afni", "--input-dir", str(tmp_path), "--task", "rest",
                                         "--prefix", "sub-", "--output-dir", str(tmp_path / "out")])
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "out" / "autorate.csv", dtype=str)
        assert out.loc[0, ["qsumm", "rater_FINAL"]].tolist() == ["other", "bad"]
        assert "FINAL_comment" not in out.columns


class TestDecisions:

    def test_far_below_the_bad_cutoff_is_included_and_near_it_goes_to_a_person(self):
        near = {"cens_frac": 0.25, "vstat_rating": "other", "regr_rating": "other", "radcor_rating": "other"}
        table = rated({}, near)
        assert table.decision.tolist() == ["include", "person"]
        assert table.score.tolist() == [0, 9]
        assert table.loc[1, "reason"] == "score 9 within 3 of the bad cutoff 10.5"

    def test_an_image_section_rated_bad_goes_to_a_person_when_the_numbers_are_not_bad(self):
        table = rated({"vstat_rating": "bad", "radcor_rating": "bad", "regr_rating": "bad"})
        assert table.loc[0, "decision"] == "person"
        assert table.loc[0, "reason"] == "vstat, regr, radcor rated bad while the numbers are not bad"

    def test_a_clear_motion_failure_excludes(self):
        table = rated({"cens_frac": 0.45})
        assert table.loc[0, ["decision", "FINAL"]].tolist() == ["exclude", "bad"]
        assert table.loc[0, "reason"] == "veto: cens_frac past its bad line; mot bad"

    def test_just_past_the_tolerance_goes_to_a_person_unless_the_score_is_bad_anyway(self):
        just_past = {"cens_mot": 0.17}
        bad_images = {"vstat_rating": "bad", "regr_rating": "bad", "radcor_rating": "bad"}
        table = rated(just_past, {**just_past, **bad_images})
        assert table.decision.tolist() == ["person", "exclude"]
        assert table.loc[0, "reason"].startswith("cens_mot just past the tolerance")

    def test_runs_without_image_ratings_go_to_a_person_unless_vetoed(self):
        unrated = {"vstat_rating": None, "radcor_rating": None}
        table = rated(unrated, {**unrated, "cens_frac": 0.45}, {"vstat_rating": None})
        assert table.decision.tolist() == ["person", "exclude", "person"]
        assert table.loc[0, "reason"] == "not rated: vstat, radcor"
        # With vstat alone unrated, even a bad vstat keeps the score under the other cutoff
        assert table.FINAL.tolist()[1:] == ["bad", "good"] and pd.isna(table.loc[0, "FINAL"])

    def test_the_checks_are_a_share_of_each_automatic_group(self):
        decisions = pd.Series(["include"] * 25 + ["exclude"] * 5 + ["person"] * 4)
        check = mark_checks(decisions, 0.1)
        assert check[decisions == "include"].eq("yes").sum() == 3
        assert check[decisions == "exclude"].eq("yes").sum() == 1
        assert check[decisions == "person"].eq("").all()
        assert check.equals(mark_checks(decisions, 0.1))


class TestPolicy:

    @pytest.mark.parametrize("change,message", [
        ({"extra": 1}, "unknown field"),
        ({"margin": None}, "missing margin"),
        ({"metrics": {"flip_guess": {"tolerance": 0.1}}}, "needs a threshold"),
        ({"metrics": {"GCOR": {"tolerance": "ten%"}}}, "percentage"),
        ({"veto_sections": ["vstat"]}, "veto_sections"),
        ({"cutoffs": {"bad": 5, "other": 5}}, "must be below"),
        ({"weights": {"vstats": 1}}, "not an APQC section"),
        ({"mot": "fd"}, "mot must name"),
        ({"spot_check": 2}, "share"),
    ])
    def test_mistakes_are_named(self, change, message):
        config = load_config(default_config_path("afni"))
        block = {**default_block(), **change}
        block = {k: v for k, v in block.items() if v is not None}
        with pytest.raises(ConfigError, match=message):
            parse_policy(block, config.metrics)

    def test_settings_for_a_metric_without_thresholds_are_noted_not_refused(self, tmp_path):
        raw = json.loads(default_config_path("afni").read_text(encoding="utf-8"))
        del raw["metrics"]["GCOR"]
        path = tmp_path / "afni_config.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        _, policy, _, notes = load(path)
        assert policy.unused == ("GCOR",) and "GCOR" in notes[0]

    def test_a_config_without_autorate_settings_uses_the_defaults_and_says_so(self, tmp_path):
        path = tmp_path / "afni_config.json"
        path.write_text(json.dumps({"metrics": {"cens_frac": {"bad": ">= 0.3"}}}), encoding="utf-8")
        config, policy, _, notes = load(path)
        assert policy.cut_bad == 10.5 and config.metrics["cens_frac"].rules == {"bad": (">=", 0.3)}
        assert "no autorate settings" in notes[0]


class TestCalibration:

    def test_kappa_is_one_when_all_agree_and_zero_for_one_level_throughout(self):
        y = np.array([0, 1, 2, 2])
        kappa, accuracy = kappa_accuracy(y, np.array([[0, 1, 2, 2], [2, 2, 2, 2]]))
        assert kappa.tolist() == [1.0, 0.0] and accuracy.tolist() == [1.0, 0.5]

    def test_the_cutoffs_that_reproduce_the_ratings_are_chosen(self):
        scores = np.arange(0, 15, 1.0)
        y = np.where(scores >= 9, 2, np.where(scores >= 4, 1, 0))
        bad, other, kappa, accuracy = choose(y, scores, np.zeros(15, bool), (10.5, 5))
        assert (bad, other, kappa, accuracy) == (8.5, 3.5, 1.0, 1.0)

    def test_two_cutoffs_can_share_a_gap_when_no_run_is_rated_other(self):
        scores = np.array([0, 1, 2, 10, 11.0])
        bad, other, kappa, _ = choose(np.array([0, 0, 0, 2, 2]), scores, np.zeros(5, bool), (10.5, 5))
        assert 2 < other < bad < 10 and kappa == 1.0

    def test_among_equal_pairs_the_one_nearest_the_current_cutoffs_wins(self):
        # The only bad run is vetoed, so any bad cutoff above 5 reproduces the ratings
        scores, y, veto = np.array([0, 1, 5, 9.0]), np.array([0, 0, 1, 2]), np.array([False, False, False, True])
        assert choose(y, scores, veto, (10.5, 5))[:2] == (9.5, 3.0)
        assert choose(y, scores, veto, (7, 3))[:2] == (7.0, 3.0)

    def test_calibrating_saves_the_cutoffs_and_keeps_the_rest_of_the_file(self, tmp_path):
        path = tmp_path / "afni_config.json"
        path.write_text(default_config_path("afni").read_text(encoding="utf-8"), encoding="utf-8")
        config, policy = default(calibration={"min_runs": 4, "min_good": 1})
        df = runs({"FINAL_rating": "good"}, {"FINAL_rating": "good", "vstat_rating": "other"},
                  {"cens_frac": 0.25, "vstat_rating": "other", "FINAL_rating": "other"},
                  {"cens_frac": 0.25, "vstat_rating": "bad", "radcor_rating": "bad", "FINAL_rating": "bad"})
        lines = calibrate_config(df, config, policy, path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        before = json.loads(default_config_path("afni").read_text(encoding="utf-8"))
        assert saved["autorate"]["cutoffs"] == {"bad": 9, "other": 4.5}
        assert {**saved["autorate"], "cutoffs": None} == {**before["autorate"], "cutoffs": None}
        assert saved["metrics"] == before["metrics"]
        assert path.with_name("afni_config.json.bak").exists()
        assert "kappa 1.00" in lines[2]

    @pytest.mark.parametrize("changes,message", [
        ([{"FINAL_rating": "good"}] * 2 + [{"FINAL_rating": "bad", "cens_frac": 0.45}], "at least 4 are needed"),
        ([{"FINAL_rating": "other"}] * 3 + [{"FINAL_rating": "bad", "cens_frac": 0.45}], "at least 1 are needed"),
        ([{"FINAL_rating": "good"}] * 4, "none of them is rated bad"),
    ])
    def test_too_few_ratings_are_refused(self, tmp_path, changes, message):
        config, policy = default(calibration={"min_runs": 4, "min_good": 1})
        with pytest.raises(CalibrationError, match=message):
            calibrate_config(runs(*changes), config, policy, tmp_path / "afni_config.json")
        assert not (tmp_path / "afni_config.json").exists()


class TestCommand:

    def write_runs(self, root, df):
        for _, row in df.iterrows():
            info = root / "rest_output" / f"QC_sub-{row.ID}" / "extra_info"
            info.mkdir(parents=True)
            fields = {"censor fraction": row.cens_frac, "global correlation (GCOR)": row.GCOR,
                      "flip guess": "NO_FLIP", "average censored motion": row.cens_mot,
                      **{f"{s} rating": row[f"{s}_rating"] for s in (*RATED, "FINAL") if pd.notna(row.get(f"{s}_rating"))}}
            (info / f"out.ss_review.sub-{row.ID}.json").write_text(json.dumps({k: str(v) for k, v in fields.items()}))

    def invoke(self, root, *extra):
        return runner.invoke(cli.app, ["autorate", "afni", "--input-dir", str(root), "--task", "rest",
                                       "--prefix", "sub-", "--output-dir", str(root / "out"), *extra])

    def test_it_writes_the_table_and_the_summary(self, tmp_path):
        self.write_runs(tmp_path, runs({}, {"cens_frac": 0.45}, {"vstat_rating": "other", "cens_frac": 0.25,
                                                                  "regr_rating": "bad", "radcor_rating": "bad"}))
        result = self.invoke(tmp_path)
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "out" / "autorate.csv", dtype={"ID": str})
        assert out.decision.tolist() == ["include", "exclude", "person"]
        assert list(out.columns[:6]) == ["ID", "decision", "check", "reason", "FINAL", "rater_FINAL"]
        summary = (tmp_path / "out" / "autorate_summary.txt").read_text(encoding="utf-8")
        assert re.search(r"include +1 \(33%\)", summary) and summary.strip() in result.output

    def test_calibrate_writes_the_config_the_dashboard_uses(self, tmp_path):
        config = tmp_path / "out" / "afni_config.json"
        config.parent.mkdir()
        raw = json.loads(default_config_path("afni").read_text(encoding="utf-8"))
        raw["autorate"]["calibration"] = {"min_runs": 4, "min_good": 1}
        config.write_text(json.dumps(raw), encoding="utf-8")
        self.write_runs(tmp_path, runs({"FINAL_rating": "good"}, {"FINAL_rating": "good"},
                                       {"cens_frac": 0.25, "vstat_rating": "other", "FINAL_rating": "other"},
                                       {"cens_frac": 0.45, "FINAL_rating": "bad"}))
        result = self.invoke(tmp_path, "--calibrate")
        assert result.exit_code == 0, result.output
        assert "Calibrated on 4 runs" in result.output
        assert json.loads(config.read_text(encoding="utf-8"))["autorate"]["cutoffs"] != raw["autorate"]["cutoffs"]

    def test_calibrating_with_too_few_ratings_stops_with_the_reason(self, tmp_path):
        self.write_runs(tmp_path, runs({"FINAL_rating": "good"}))
        result = self.invoke(tmp_path, "--calibrate")
        assert result.exit_code == 1
        assert "Cannot calibrate: 1 runs have a FINAL rating" in result.output
        assert not (tmp_path / "out" / "afni_config.json").exists()
