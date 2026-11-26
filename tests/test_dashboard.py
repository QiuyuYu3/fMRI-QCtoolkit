"""
Tests for the dashboards' filtering, heatmap data, sidebar and table selection.
Most callback logic is called directly; `dash_call` drives a callback through Dash's request path.
"""

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fMRI_QCtoolkit.dashboard.afni_app import AFNIDashboard
from fMRI_QCtoolkit.dashboard.base_app import BaseDashboard
from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard
from fMRI_QCtoolkit.data.base import read_csv_exact
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline
from tests.dashboard_helpers import (FD_MEAN_RANGE, afni_runs, dash_call, layout_values, make_dashboard,
                                     shown_ids)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "example_data" / "fmriprep"


class TestDefaultView:

    def test_only_runs_with_a_bad_metric_are_hidden(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "003", "005", "008"]

    def test_ticking_bad_shows_every_run(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        statuses = {column: s + ["bad"] for column, s in statuses.items()}
        assert len(shown_ids(dashboard, ranges, statuses, ratings)) == 8

    def test_unticking_other_hides_flagged_runs(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        statuses = {column: [v for v in s if v != "other"] for column, s in statuses.items()}
        assert shown_ids(dashboard, ranges, statuses, ratings) == ["001", "008"]

    def test_unticking_na_hides_missing_values(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        statuses = {column: [v for v in s if v != "NA"] for column, s in statuses.items()}
        assert "008" not in shown_ids(dashboard, ranges, statuses, ratings)

    def test_a_moved_slider_bounds_the_values_but_keeps_missing_ones(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        ranges["GCOR"] = [ranges["GCOR"][0], 0.05]
        assert shown_ids(dashboard, ranges, statuses, ratings) == ["008"]

    def test_fmriprep_tsnr_and_gcor_never_hide_a_run(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002"], "session": ["01", "01"], "run": [1, 1],
                           "fd_perc": [5.0, 5.0], "fd_mean": [0.1, 0.1], "tsnr": [20.0, 400.0],
                           "gcor": [0.5, 0.01]})
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path)
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "002"]

    def test_rating_dropdown_filters(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002", "003"], "session": ["01"] * 3, "run": [1, 1, 1],
                           "fd_mean": [0.1] * 3, "Final": ["good", "bad", None]})
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        final = dashboard.processor.checkbox_groups.index("Final")
        ratings[final] = ["good", "NA"]
        assert shown_ids(dashboard, ranges, statuses, ratings) == ["001", "003"]


class TestCustomConfig:

    def test_thresholds_come_from_the_given_file(self, tmp_path):
        config = tmp_path / "lab.json"
        config.write_text(json.dumps({"metrics": {"cens_frac": {"good": "< 0.4", "bad": ">= 0.5"}}}))
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path, config=config)

        assert [m.column for m in dashboard.metrics] == ["cens_frac"]
        assert dashboard.status["cens_frac"].unique().tolist() == ["good"]
        assert shown_ids(dashboard, *layout_values(dashboard)) == [f"00{i}" for i in range(1, 9)]


class TestOtherwise:

    def test_a_good_rule_with_otherwise_bad_hides_the_rest(self, tmp_path):
        config = tmp_path / "lab.json"
        config.write_text(json.dumps({"metrics": {"cens_frac": {"good": "< 0.15", "otherwise": "bad"},
                                                  "GCOR": {"otherwise": "other"}}}))
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path, config=config)

        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "004", "005", "006", "007", "008"]
        lines = [c.children for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Li"]
        assert lines == ["cens_frac: good < 0.15, otherwise bad", "GCOR: all other"]
        heatmap = dashboard.quantitative_heatmap_rows(dashboard.processor.get_data())
        assert set(heatmap[heatmap["Variables"] == "GCOR"]["StatusStr"]) == {"other", "NA"}


class TestSidebarText:

    @staticmethod
    def sidebar_lines(dashboard):
        return [c.children for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Li"]

    def test_each_pipeline_lists_its_own_thresholds(self, tmp_path):
        afni = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        assert "Censor Fraction: good < 0.15, bad ≥ 0.2" in self.sidebar_lines(afni)

        fmriprep = FMRIPrepDashboard(FMRIPrepPipeline.from_saved_data(EXAMPLES / "df_final.csv"))
        assert self.sidebar_lines(fmriprep) == ["% of FDs above threshold: good ≤ 15, bad > 20",
                                                "Average FD: good < 0.2, bad ≥ 0.3"]


class TestPageStyle:

    def test_dash_4_controls_take_the_dashboard_blue(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        client = dashboard.app.server.test_client()
        page = client.get(f"/?token={dashboard.gate.token}", follow_redirects=True).get_data(as_text=True)
        assert "html:root { --Dash-Fill-Interactive-Strong: #5289bd; }" in page

    def test_a_narrow_window_can_scroll_to_what_dash_4_tabs_would_clip(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        client = dashboard.app.server.test_client()
        page = client.get(f"/?token={dashboard.gate.token}", follow_redirects=True).get_data(as_text=True)
        assert ".tab-parent { overflow: visible; }" in page


class TestTableDisplay:

    def test_numbers_are_shown_with_three_decimals_but_ids_are_not(self):
        pipeline = FMRIPrepPipeline.from_saved_data(EXAMPLES / "df_final.csv", task="rest")
        columns = {c["id"]: c for c in FMRIPrepDashboard(pipeline, task="rest")._table_columns()}

        assert columns["fd_mean"]["format"].to_plotly_json()["specifier"] == ".3~f"
        assert columns["run"]["type"] == "numeric"
        assert "format" not in columns["ID"]

    def test_the_table_has_the_ids_then_the_config_metrics_in_order_then_the_ratings(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002"], "session": ["01"] * 2, "run": [1, 1], "Final": ["good"] * 2,
                           "efc": [0.5, 0.6], "fd_perc": [5.0, 25.0], "fd_mean": [0.1, 0.1],
                           "modality": ["rest"] * 2})
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {"label": "Average FD"}, "fd_perc": {"bad": "> 20"}}}),
                          encoding="utf-8")
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path, config=config)
        expected = ["ID", "session", "run", "fd_mean", "fd_perc", "Final"]

        columns = dashboard._table_columns()
        assert [c["id"] for c in columns] == expected
        # Nothing hideable, so the table has no Toggle Columns button
        assert not any("hideable" in c for c in columns)
        table = dash_call(dashboard, "datatable.data", {}, FD_MEAN_RANGE).get_json()["response"]["datatable"]
        assert [list(record) for record in table["data"]] == [expected]
        shown = dash_call(dashboard, "selected-rows-display.children",
                          {("datatable", "selected_rows"): [0], ("filtered-rows", "data"): [0]},
                          "datatable.selected_rows").get_json()["response"]["selected-rows-display"]["children"]
        assert [c["id"] for c in shown["props"]["columns"]] == expected
        assert list(shown["props"]["data"][0]) == expected
        # A few selected rows take only the room they need
        assert shown["props"]["style_table"]["maxHeight"] == "300px"
        assert "height" not in shown["props"]["style_table"]

    def test_table_only_columns_follow_the_metrics_in_data_order_and_absent_ones_are_reported(self, tmp_path):
        df = pd.DataFrame({"ID": ["001"], "Final": ["good"], "efc": [0.5], "snr": [3.0], "fd_mean": [0.1]})
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {}}, "table_columns": ["snr", "absent", "efc"]}),
                          encoding="utf-8")
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path, config=config)
        assert dashboard.table_column_ids() == ["ID", "fd_mean", "efc", "snr", "Final"]
        assert dashboard.unmatched == ["absent"]
        assert [m.column for m in dashboard.metrics] == ["fd_mean"]


class TestPlotsAreDrawnOnDemand:

    @staticmethod
    def heatmaps(dashboard, positions, tab, drawn=None):
        return dash_call(dashboard, "quantitative-heatmap.figure",
                         {("filtered-rows", "data"): positions, ("main-tabs", "value"): tab,
                          ("heatmap-rows", "data"): drawn}, "filtered-rows.data")

    @staticmethod
    def lollipop(dashboard, tab, drawn=None):
        return dash_call(dashboard, "lollipop-chart.figure",
                         {("main-tabs", "value"): tab, ("lollipop-drawn", "data"): drawn}, "main-tabs.value")

    def test_nothing_is_drawn_on_the_table_tab(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        assert self.heatmaps(dashboard, [0, 2], "table-tab").status_code == 204
        assert self.lollipop(dashboard, "table-tab").status_code == 204

    def test_heatmaps_show_the_filtered_rows_when_the_plots_tab_opens(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        response = self.heatmaps(dashboard, [0, 2], "plots-tab").get_json()["response"]
        assert response["heatmap-rows"]["data"] == [0, 2]
        assert response["quantitative-heatmap"]["figure"]["layout"]["xaxis"]["ticktext"] == ["001", "003"]
        assert "qualitative-heatmap" in response

    def test_heatmaps_are_redrawn_only_when_the_rows_change(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        assert self.heatmaps(dashboard, [0, 2], "plots-tab", drawn=[0, 2]).status_code == 204
        assert self.heatmaps(dashboard, [0, 2], "plots-tab", drawn=[0, 1, 2]).status_code == 200

    def test_the_lollipop_is_drawn_once(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        response = self.lollipop(dashboard, "plots-tab").get_json()["response"]
        assert response["lollipop-drawn"]["data"] is True
        assert response["lollipop-chart"]["figure"]["data"]
        assert self.lollipop(dashboard, "plots-tab", drawn=True).status_code == 204


@pytest.fixture
def fmriprep_dashboard(tmp_path):
    def build(df):
        return make_dashboard(FMRIPrepDashboard, df, tmp_path)
    return build


class TestQuantitativeHeatmapRows:

    def test_one_row_per_run_and_thresholded_metric(self, fmriprep_dashboard):
        df = pd.DataFrame({"ID": ["001", "002"], "session": ["01", "02"], "run": [1, 1],
                           "fd_mean": [0.2, 0.8], "fd_perc": [1.0, 1.0], "tsnr": [0.9, 0.1]})
        dashboard = fmriprep_dashboard(df)

        rows = dashboard.quantitative_heatmap_rows(dashboard.processor.get_data())

        assert len(rows) == 4
        assert rows["Variables"].tolist() == ["fd_perc", "fd_perc", "fd_mean", "fd_mean"]

    def test_status_string_and_number_agree(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001"], "session": ["01"], "run": [1],
                                                     "fd_mean": [0.8]}))

        row = dashboard.quantitative_heatmap_rows(dashboard.processor.get_data()).iloc[0]

        assert row["StatusStr"] == "bad"
        assert row["Status"] == BaseDashboard.STATUS_TO_NUM["bad"]

    def test_missing_value_is_na(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001", "002"], "session": ["01", "01"],
                                                     "run": [1, 2], "fd_mean": [np.nan, 0.1]}))

        row = dashboard.quantitative_heatmap_rows(dashboard.processor.get_data()).iloc[0]

        assert np.isnan(row["Value"])
        assert row["StatusStr"] == "NA"

    def test_session_and_run_are_carried_through(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001", "002"], "session": ["02", "pre"],
                                                     "run": [3, 1], "fd_mean": [0.1, 0.1]}))

        rows = dashboard.quantitative_heatmap_rows(dashboard.processor.get_data())

        assert rows[["session", "run"]].values.tolist() == [["02", 3], ["pre", 1]]

    def test_absent_or_missing_session_and_run_default_to_one(self, tmp_path):
        absent = make_dashboard(FMRIPrepDashboard, pd.DataFrame({"ID": ["001"], "fd_mean": [0.1]}), tmp_path)
        rows = absent.quantitative_heatmap_rows(absent.processor.get_data())
        assert rows[["session", "run"]].values.tolist() == [["1", 1]]

        missing = make_dashboard(FMRIPrepDashboard, pd.DataFrame(
            {"ID": ["001"], "session": [np.nan], "run": [np.nan], "fd_mean": [0.1]}), tmp_path)
        rows = missing.quantitative_heatmap_rows(missing.processor.get_data())
        assert rows[["session", "run"]].values.tolist() == [["1", 1]]

    def test_filtered_subset_uses_its_own_rows(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001", "002"], "session": ["01", "01"],
                                                     "run": [1, 2], "fd_mean": [0.1, 0.8]}))
        subset = dashboard.processor.get_data().iloc[[1]]

        rows = dashboard.quantitative_heatmap_rows(subset)

        assert rows[["ID", "run", "StatusStr"]].values.tolist() == [["002", 2, "bad"]]

    def test_no_thresholded_metric_gives_no_rows(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001"], "session": ["01"], "run": [1],
                                                     "tsnr": [50.0]}))

        assert dashboard.quantitative_heatmap_rows(dashboard.processor.get_data()).empty


class TestQualitativeHeatmapRows:

    def test_one_row_per_run_and_rated_section(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001", "002"], "session": ["01", "01"],
                                                     "run": [1, 2], "SDC": ["good", "bad"],
                                                     "Align": ["other", None]}))

        rows = dashboard.qualitative_heatmap_rows(dashboard.processor.get_data())

        assert rows["StatusStr"].tolist() == ["other", "NA", "good", "bad"]
        assert rows["Status"].tolist() == [2, 0, 3, 1]

    def test_unknown_rating_falls_back_to_zero(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001"], "session": ["01"], "run": [1],
                                                     "SDC": ["weird"]}))

        row = dashboard.qualitative_heatmap_rows(dashboard.processor.get_data()).iloc[0]

        assert (row["StatusStr"], row["Status"]) == ("weird", 0)

    def test_no_rated_sections_gives_no_rows(self, fmriprep_dashboard):
        dashboard = fmriprep_dashboard(pd.DataFrame({"ID": ["001"], "session": ["01"], "run": [1],
                                                     "fd_mean": [0.1]}))

        assert dashboard.qualitative_heatmap_rows(dashboard.processor.get_data()).empty


class TestCarrySelection:
    """Selections are indices into the filtered table; the store keeps each row's position in the full table."""

    def test_follows_rows_when_the_filter_removes_others(self):
        assert BaseDashboard._carry_selection([0, 1, 2, 3], [1, 2], [1, 2, 3]) == [0, 1]

    def test_rows_filtered_out_are_dropped(self):
        assert BaseDashboard._carry_selection([0, 1, 2, 3], [0], [3]) == []

    def test_rows_that_come_back_stay_unselected(self):
        assert BaseDashboard._carry_selection([1, 2], [0], [0, 1, 2]) == [1]

    def test_indices_past_the_previous_table_are_ignored(self):
        assert BaseDashboard._carry_selection([5], [0, 3], [5]) == [0]

    def test_nothing_selected(self):
        assert BaseDashboard._carry_selection(None, [], [0, 1]) == []


def precise_runs():
    return pd.DataFrame({"ID": ["001", "002", "003"], "session": ["01"] * 3, "run": [1, 1, 1],
                         "fd_perc": [1.0, 2.0, 3.0], "fd_mean": [0.123456789012345, 0.2, 0.25]})


class TestSelectedRows:

    def test_selection_reads_the_loaded_table_at_full_precision(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        rows = dashboard.selected_data([0, 2], [1, 0])
        assert rows["ID"].tolist() == ["003", "001"]
        assert rows["fd_mean"].tolist() == [0.25, 0.123456789012345]

    def test_download_keeps_full_precision(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "download-dataframe-csv.data",
                         {("download-button", "n_clicks"): 1, ("datatable", "selected_rows"): [0],
                          ("filtered-rows", "data"): [0, 2]}, "download-button.n_clicks")
        csv = resp.get_json()["response"]["download-dataframe-csv"]["data"]["content"]
        rows = read_csv_exact(io.StringIO(csv), dtype={"ID": str})
        assert rows["ID"].tolist() == ["001"]
        assert rows["fd_mean"].tolist() == [0.123456789012345]

    @pytest.mark.parametrize("button, expected", [("select-all-button", [0, 1]), ("clear-selection-button", [])])
    def test_buttons_change_the_selection_without_resending_the_table(self, tmp_path, button, expected):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "datatable.data",
                         {("filtered-rows", "data"): [0, 2], ("datatable", "selected_rows"): [1],
                          (button, "n_clicks"): 1}, f"{button}.n_clicks")
        assert resp.get_json()["response"] == {"datatable": {"selected_rows": expected}}

    def test_a_filter_change_sends_the_table_but_no_plots(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "datatable.data", {}, FD_MEAN_RANGE)
        assert set(resp.get_json()["response"]) == {"datatable", "filtered-rows"}

    def test_a_filter_change_stores_positions_and_keeps_the_selected_run(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "datatable.data",
                         {("filtered-rows", "data"): [1, 2], ("datatable", "selected_rows"): [1]},
                         FD_MEAN_RANGE)
        response = resp.get_json()["response"]
        assert response["filtered-rows"]["data"] == [0, 1, 2]
        assert [r["ID"] for r in response["datatable"]["data"]] == ["001", "002", "003"]
        assert response["datatable"]["selected_rows"] == [2]
