"""
Unit tests for BaseDashboard's heatmap row building.
These run without constructing a Dash app; the callbacks themselves are not covered.
"""

import pytest
import pandas as pd
from fMRI_QCtoolkit.dashboard.base_app import BaseDashboard


class StubProcessor:
    def __init__(self, checkbox_groups):
        self.checkbox_groups = checkbox_groups


class StubDashboard(BaseDashboard):
    """Concrete dashboard that skips Dash app construction."""

    def __init__(self, checkbox_groups=()):
        self.processor = StubProcessor(list(checkbox_groups))
        self.task = "test"
        self.config = {}

    def _get_config_filename(self):
        return "fmriprep_config.json"

    def assign_status(self, value, variable_name):
        if pd.isna(value):
            return "NA"
        return "bad" if value > 0.5 else "good"

    def get_variable_labels(self):
        return {}, {}

    def get_filter_components(self):
        return []


@pytest.fixture
def dashboard():
    return StubDashboard(checkbox_groups=["SDC", "Align"])


class TestQuantitativeHeatmapRows:

    def test_one_row_per_subject_and_variable(self, dashboard):
        df = pd.DataFrame({"ID": ["001", "002"], "session": [1, 2], "run": [1, 1],
                           "fd_mean": [0.2, 0.8], "tsnr": [0.9, 0.1]})

        rows = dashboard.quantitative_heatmap_rows(df, ["fd_mean", "tsnr"])

        assert len(rows) == 4
        assert [r["Variables"] for r in rows] == ["fd_mean", "tsnr", "fd_mean", "tsnr"]

    def test_status_string_and_number_agree(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "fd_mean": [0.8]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert row["StatusStr"] == "bad"
        assert row["Status"] == BaseDashboard.STATUS_TO_NUM["bad"]

    def test_missing_value_becomes_none(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "fd_mean": [float("nan")]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert row["Value"] is None
        assert row["StatusStr"] == "NA"

    def test_session_and_run_are_carried_through(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": ["02"], "run": [3], "fd_mean": [0.1]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert (row["session"], row["run"]) == ("02", 3)

    def test_non_numeric_session_label_is_kept(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": ["pre"], "run": [1], "fd_mean": [0.1]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert row["session"] == "pre"

    def test_absent_session_and_run_default_to_one(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "fd_mean": [0.1]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert (row["session"], row["run"]) == ("1", 1)

    def test_missing_session_and_run_default_to_one(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [float("nan")],
                           "run": [float("nan")], "fd_mean": [0.1]})

        row = dashboard.quantitative_heatmap_rows(df, ["fd_mean"])[0]

        assert (row["session"], row["run"]) == ("1", 1)

    def test_no_variables_gives_no_rows(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "fd_mean": [0.1]})

        assert dashboard.quantitative_heatmap_rows(df, []) == []


class TestQualitativeHeatmapRows:

    def test_one_row_per_subject_and_rated_module(self, dashboard):
        df = pd.DataFrame({"ID": ["001", "002"], "session": [1, 1], "run": [1, 2],
                           "SDC": ["good", "bad"], "Align": ["other", "NA"]})

        rows = dashboard.qualitative_heatmap_rows(df)

        assert len(rows) == 4
        assert [r["StatusStr"] for r in rows] == ["good", "other", "bad", "NA"]
        assert [r["Status"] for r in rows] == [3, 2, 1, 0]

    def test_columns_absent_from_the_frame_are_skipped(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "SDC": ["good"]})

        rows = dashboard.qualitative_heatmap_rows(df)

        assert [r["Variables"] for r in rows] == ["SDC"]

    def test_missing_rating_becomes_na(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1],
                           "SDC": [None], "Align": ["good"]})

        rows = dashboard.qualitative_heatmap_rows(df)

        assert rows[0]["StatusStr"] == "NA"
        assert rows[0]["Status"] == 0

    def test_unknown_rating_falls_back_to_zero(self, dashboard):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "SDC": ["weird"]})

        row = dashboard.qualitative_heatmap_rows(df)[0]

        assert row["StatusStr"] == "weird"
        assert row["Status"] == 0

    def test_no_checkbox_groups_gives_no_rows(self):
        df = pd.DataFrame({"ID": ["001"], "session": [1], "run": [1], "SDC": ["good"]})

        assert StubDashboard().qualitative_heatmap_rows(df) == []
