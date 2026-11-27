"""
Tests for 'fmriqc prep custom': sorting columns by their values, reading and merging the tables, and the errors.
"""

import numpy as np
import pandas as pd
import pytest

from fMRI_QCtoolkit.data.custom_pipeline import CustomPipeline, classify_columns, normalize_columns, odd_values


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def prep(tmp_path, *files):
    return CustomPipeline(files, tmp_path / "out").process().df_final


class TestClassifyColumns:

    def table(self):
        return pd.DataFrame({
            "ID": ["001", "002", "003", "004"],
            "run": [1, 1, 1, 1],
            "Final": ["Good", " bad ", None, ""],
            "SDC": ["good", "other", "good", "bad"],
            "fd_mean": [0.1, 0.2, np.nan, 0.4],
            "typed": ["0.5", " 2 ", None, ""],
            "verdict": ["pass", "fail", "pass", None],
            "typo": ["good", "goood", "bad", None],
            "empty": [None, None, "", " "],
            "flag": [True, False, True, False],
        })

    def test_ratings_metrics_and_table_only(self):
        assert classify_columns(self.table()) == (
            ["Final", "SDC"], ["fd_mean", "typed"], ["verdict", "typo", "empty", "flag"])

    def test_ratings_are_lower_case_and_metrics_numbers(self):
        df = normalize_columns(self.table(), ["Final", "SDC"], ["fd_mean", "typed"])
        assert df["Final"].tolist()[:2] == ["good", "bad"] and df["Final"].iloc[2:].isna().all()
        assert df["typed"].tolist()[:2] == [0.5, 2.0] and df["typed"].iloc[2:].isna().all()
        assert df["verdict"].tolist()[:2] == ["pass", "fail"]

    @pytest.mark.parametrize("values,text", [
        (["pass", "fail", "pass", None], "pass (2 rows), fail (1 row)"),
        (["good", "goood", "bad"], "goood (1 row)"),
        ([None, " "], "empty"),
        (["good", "3"], "mixes numbers with good, other or bad"),
        (["a", "b", "c", "d", "d"], "d (2 rows), a (1 row), b (1 row) and 1 more"),
    ])
    def test_table_only_columns_name_the_values_that_kept_them_out(self, values, text):
        assert odd_values(pd.Series(values, dtype=object)) == text


class TestReading:

    def test_one_file(self, tmp_path):
        df = prep(tmp_path, write(tmp_path / "qc.csv", "ID,Final,fd_mean\n001,GOOD,0.1\n002, bad ,0.3\n"))
        assert df.to_dict("list") == {"ID": ["001", "002"], "Final": ["good", "bad"], "fd_mean": [0.1, 0.3]}
        assert (tmp_path / "out" / "df_final.csv").read_text().splitlines()[1] == "001,good,0.1"

    def test_empty_names_left_by_a_spreadsheet_are_not_repeats(self, tmp_path):
        df = prep(tmp_path, write(tmp_path / "qc.csv", "﻿ID,Final,,\n001,good,,\n002,bad,,\n"))
        assert df["Final"].tolist() == ["good", "bad"]

    def test_a_tsv_is_read_with_tabs_and_bids_labels_lose_their_prefixes(self, tmp_path):
        df = prep(tmp_path, write(tmp_path / "qc.tsv", "ID\tsession\trun\tsnr\nsub-01\tses-pre\trun-02\t5\n"))
        assert df[["ID", "session", "run"]].values.tolist() == [["01", "pre", 2]]

    @pytest.mark.parametrize("name,text,message", [
        ("qc.txt", "ID\n1\n", "qc.txt: give a .csv or .tsv file"),
        ("qc.csv", "subject,snr\n1,5\n", "qc.csv: no ID column; name the participant column ID"),
        ("qc.csv", "ID,snr\n001,5\n,6\n", "qc.csv: ID is empty on line(s) 3"),
        ("qc.csv", "ID,run,snr\n001,a,5\n001,1.5,6\n", "qc.csv: run must be a whole number, not 1.5, a"),
        ("qc.csv", "ID,run,snr\n001,1,5\n001,run-1,6\n002,1,5\n002,1,6\n",
         "qc.csv: more than one row for ID 001, run 1; ID 002, run 1"),
        ("qc.csv", "ID,Final,snr,Final,snr,snr\n001,good,5,bad,6,7\n",
         "qc.csv: more than one column named Final, snr. Give each column its own name."),
    ])
    def test_a_file_that_cannot_be_used_is_named_with_the_problem(self, tmp_path, name, text, message):
        with pytest.raises(ValueError) as error:
            prep(tmp_path, write(tmp_path / name, text))
        assert str(error.value) == message


class TestMerging:

    def test_files_are_matched_on_id_session_and_run(self, tmp_path, capsys):
        ratings = write(tmp_path / "ratings.csv", "ID,session,run,Final\nsub-001,ses-1,run-01,good\n002,1,1,bad\n")
        metrics = write(tmp_path / "metrics.csv", "ID,session,run,fd_mean\n001,1,1,0.1\n002,1,1,0.2\n003,1,1,0.3\n")
        df = prep(tmp_path, ratings, metrics)
        assert df.to_dict("list") == {"ID": ["001", "002", "003"], "session": ["1", "1", "1"], "run": [1, 1, 1],
                                      "Final": ["good", "bad", np.nan], "fd_mean": [0.1, 0.2, 0.3]}
        assert "2 rows matched, 0 only in ratings.csv, 1 only in metrics.csv" in capsys.readouterr().out

    def test_a_file_per_participant_goes_to_each_of_its_runs(self, tmp_path):
        runs = write(tmp_path / "runs.csv", "ID,run,fd_mean\n001,1,0.1\n001,2,0.2\n")
        people = write(tmp_path / "people.tsv", "ID\tage\nsub-001\t21\nsub-099\t40\n")
        df = prep(tmp_path, runs, people)
        assert df[["ID", "run", "age"]].astype(object).where(df.notna(), None).values.tolist() == [
            ["001", 1, 21], ["001", 2, 21], ["099", None, 40]]

    def test_nothing_matched_is_a_warning_that_shows_both_sides(self, tmp_path, capsys):
        df = prep(tmp_path, write(tmp_path / "a.csv", "ID,x\n1,5\n"), write(tmp_path / "b.csv", "ID,y\n001,6\n"))
        out = capsys.readouterr().out
        assert "WARNING: no row of b.csv matched!" in out
        assert "ID: a.csv=['1'] vs b.csv=['001']" in out
        assert len(df) == 2

    def test_a_column_in_two_files_is_refused(self, tmp_path):
        a = write(tmp_path / "a.csv", "ID,fd_mean,Final\n001,0.1,good\n")
        b = write(tmp_path / "b.csv", "ID,fd_mean,Final\n001,0.1,good\n")
        with pytest.raises(ValueError, match=r"Columns in more than one file: fd_mean \(a.csv, b.csv\); "
                                             r"Final \(a.csv, b.csv\)\. Keep each column in one file\."):
            prep(tmp_path, a, b)

    def test_rows_are_sorted_by_id_session_and_run(self, tmp_path):
        df = prep(tmp_path, write(tmp_path / "a.csv", "ID,session,run,x\n10,2,1,1\n9,2,2,1\n9,10,1,1\n9,2,1,1\n"))
        assert df[["ID", "session", "run"]].values.tolist() == [
            ["9", "2", 1], ["9", "2", 2], ["9", "10", 1], ["10", "2", 1]]


class TestWhatPrepPrints:

    def test_the_three_kinds_of_column_and_what_kept_a_column_out(self, tmp_path, capsys):
        prep(tmp_path, write(tmp_path / "a.csv", "ID,Final,Align,fd_mean,notes\n"
                                                 "001,pass,good,0.1,moved\n002,fail,goood,0.2,\n003,pass,bad,0.3,\n"))
        out = capsys.readouterr().out
        assert "Ratings (filter and heatmap): none" in out
        assert "Metrics (slider): fd_mean" in out
        assert "Table only: Final, Align, notes" in out
        assert "  Final: pass (2 rows), fail (1 row)" in out
        assert "  Align: goood (1 row)" in out
        assert "change its values to good, other or bad and run this command again" in out
