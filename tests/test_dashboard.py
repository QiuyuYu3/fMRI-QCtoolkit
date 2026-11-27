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
from fMRI_QCtoolkit.dashboard.custom_app import CustomDashboard
from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard
from fMRI_QCtoolkit.dashboard.settings import config_rows
from fMRI_QCtoolkit.data.base import read_csv_exact
from fMRI_QCtoolkit.data.custom_pipeline import CustomPipeline
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline
from tests.dashboard_helpers import (FD_MEAN_RANGE, afni_runs, dash_call, layout_components, layout_values,
                                     make_dashboard, shown_ids)

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
        final = dashboard.rating_columns().index("Final")
        ratings[final] = ["good", "NA"]
        assert shown_ids(dashboard, ranges, statuses, ratings) == ["001", "003"]

    def test_only_the_ratings_in_the_data_get_a_filter(self, tmp_path):
        df = afni_runs().assign(mot_rating="good", mecho_rating=["good"] * 7 + ["bad"])
        dashboard = make_dashboard(AFNIDashboard, df, tmp_path)
        dropdowns = [c.id for c in layout_components(dashboard) if isinstance(c.id, str) and c.id.endswith("_dropdown")]
        assert dropdowns == ["mot_rating_dropdown", "mecho_rating_dropdown"]
        assert set(dashboard.RATING_LABELS) == set(dashboard.processor.checkbox_groups)

        response = dash_call(dashboard, "datatable.rowData", {("mecho_rating_dropdown", "value"): ["good"]},
                             "mecho_rating_dropdown.value").get_json()["response"]
        assert [row["ID"] for row in response["datatable"]["rowData"]] == ["001", "003", "005"]

    def test_an_infinite_value_is_rated_and_leaves_the_slider_and_lollipop_to_the_others(self, tmp_path):
        df = afni_runs()
        df.loc[0, "cens_frac"] = np.inf
        dashboard = make_dashboard(AFNIDashboard, df, tmp_path)
        assert dashboard.status["cens_frac"].iloc[0] == "bad"
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["003", "005", "008"]
        lollipop = dashboard.processor.get_lollipop_data()
        scaled = lollipop[lollipop["Variable"] == "cens_frac"].set_index("ID")["Value"]
        assert np.isnan(scaled["001"]) and np.isfinite(scaled.drop("001")).all()


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
        columns = {c["field"]: c for c in FMRIPrepDashboard(pipeline, task="rest")._table_columns()}

        assert "d3.format('.3~f')" in columns["fd_mean"]["valueFormatter"]["function"]
        assert "valueFormatter" in columns["run"]
        assert "valueFormatter" not in columns["ID"]

    def test_the_id_columns_stay_on_the_left(self):
        pipeline = FMRIPrepPipeline.from_saved_data(EXAMPLES / "df_final.csv", task="rest")
        columns = FMRIPrepDashboard(pipeline, task="rest")._table_columns()
        assert [c["field"] for c in columns if c.get("pinned") == "left"] == ["ID", "session", "run"]

    def test_the_table_has_the_ids_then_the_config_metrics_in_order_then_the_ratings(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002"], "session": ["01"] * 2, "run": [1, 1], "Final": ["good"] * 2,
                           "efc": [0.5, 0.6], "fd_perc": [5.0, 25.0], "fd_mean": [0.1, 0.1],
                           "task": ["rest"] * 2})
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {"label": "Average FD"}, "fd_perc": {"bad": "> 20"}}}),
                          encoding="utf-8")
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path, config=config)
        expected = ["ID", "session", "run", "fd_mean", "fd_perc", "Final"]

        assert [c["field"] for c in dashboard._table_columns()] == expected
        response = dash_call(dashboard, "datatable.rowData", {}, FD_MEAN_RANGE).get_json()["response"]
        table = response["datatable"]
        assert [list(record) for record in table["rowData"]] == [expected + ["_row"]]
        shown = dash_call(dashboard, "selected-rows-display.children",
                          {("datatable", "selectedRows"): table["rowData"],
                           ("filtered-rows", "data"): response["filtered-rows"]["data"]},
                          "datatable.selectedRows").get_json()["response"]["selected-rows-display"]["children"]
        assert [c["field"] for c in shown["props"]["columnDefs"]] == expected
        assert list(shown["props"]["rowData"][0]) == expected

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

    @staticmethod
    def panel_titles(figure):
        return [a["text"] for a in figure["layout"].get("annotations", [])]

    def test_afni_sessions_get_one_panel_each(self, tmp_path):
        df = pd.concat([afni_runs().assign(session="01"), afni_runs().assign(session="02")])
        dashboard = make_dashboard(AFNIDashboard, df, tmp_path)
        heatmap = self.heatmaps(dashboard, [0, 8], "plots-tab").get_json()["response"]["quantitative-heatmap"]
        lollipop = self.lollipop(dashboard, "plots-tab").get_json()["response"]["lollipop-chart"]
        assert self.panel_titles(heatmap["figure"]) == ["Session 01", "Session 02"]
        assert self.panel_titles(lollipop["figure"]) == ["Session 01", "Session 02"]

    def test_afni_without_sessions_keeps_one_panel(self, tmp_path):
        dashboard = make_dashboard(AFNIDashboard, afni_runs(), tmp_path)
        heatmap = self.heatmaps(dashboard, [0, 2], "plots-tab").get_json()["response"]["quantitative-heatmap"]
        assert self.panel_titles(heatmap["figure"]) == ["Run 1"]


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


def precise_runs():
    return pd.DataFrame({"ID": ["001", "002", "003"], "session": ["01"] * 3, "run": [1, 1, 1],
                         "fd_perc": [1.0, 2.0, 3.0], "fd_mean": [0.123456789012345, 0.2, 0.25]})


class TestSelectedRows:
    """Each row's id is its position; Selected Rows and the download keep only selected rows the filters show."""

    def test_each_row_carries_its_position_in_the_full_table(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        assert [r["_row"] for r in dashboard.table_records([0, 2])] == ["0", "2"]
        grid = next(c for c in dashboard.build_layout()._traverse() if getattr(c, "id", None) == "datatable")
        assert grid.getRowId == "params.data._row"

    def test_selection_reads_the_loaded_table_at_full_precision_in_table_order(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        rows = dashboard.selected_data(dashboard.table_records([2, 0]))
        assert rows["ID"].tolist() == ["001", "003"]
        assert rows["fd_mean"].tolist() == [0.123456789012345, 0.25]

    def test_download_keeps_full_precision(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "download-dataframe-csv.data",
                         {("download-button", "n_clicks"): 1, ("datatable", "selectedRows"): dashboard.table_records([0]),
                          ("filtered-rows", "data"): [0, 1, 2]},
                         "download-button.n_clicks")
        csv = resp.get_json()["response"]["download-dataframe-csv"]["data"]["content"]
        rows = read_csv_exact(io.StringIO(csv), dtype={"ID": str})
        assert rows["ID"].tolist() == ["001"]
        assert rows["fd_mean"].tolist() == [0.123456789012345]

    def test_download_with_nothing_selected_says_so(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "download-dataframe-csv.data", {("download-button", "n_clicks"): 1},
                         "download-button.n_clicks")
        assert "No row selected." in resp.get_json()["response"]["download-dataframe-csv"]["data"]["content"]

    def test_selected_rows_the_filters_hide_are_left_out(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        assert dashboard.selected_data(dashboard.table_records([0, 2]), [1, 2])["ID"].tolist() == ["003"]

    def test_a_selection_the_filters_hide_entirely_is_neither_shown_nor_downloaded(self, tmp_path):
        # The grid keeps such rows in selectedRows, so the filtered positions decide
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        values = {("datatable", "selectedRows"): dashboard.table_records([0]), ("filtered-rows", "data"): [1, 2],
                  ("download-button", "n_clicks"): 1}
        shown = dash_call(dashboard, "selected-rows-display.children", values, "filtered-rows.data")
        assert shown.get_json()["response"]["selected-rows-display"]["children"]["props"]["children"] == \
            "No row selected."
        resp = dash_call(dashboard, "download-dataframe-csv.data", values, "download-button.n_clicks")
        assert "No row selected." in resp.get_json()["response"]["download-dataframe-csv"]["data"]["content"]

    def test_a_filter_change_sends_the_table_but_no_plots(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        resp = dash_call(dashboard, "datatable.rowData", {}, FD_MEAN_RANGE)
        assert set(resp.get_json()["response"]) == {"datatable", "filtered-rows"}

    def test_a_filter_change_stores_the_positions(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, precise_runs(), tmp_path)
        response = dash_call(dashboard, "datatable.rowData", {}, FD_MEAN_RANGE).get_json()["response"]
        assert response["filtered-rows"]["data"] == [0, 1, 2]
        assert [(r["ID"], r["_row"]) for r in response["datatable"]["rowData"]] == [("001", "0"), ("002", "1"),
                                                                                    ("003", "2")]

    def test_selected_rows_shows_every_row_without_a_scroll_box(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, pd.concat([precise_runs()] * 10, ignore_index=True), tmp_path)
        grid = dashboard.selected_grid(dashboard.processor.get_data())
        assert grid.dashGridOptions["domLayout"] == "autoHeight"
        assert grid.style == {"height": None}
        panel = next(c for c in dashboard.build_layout()._traverse()
                     if any(getattr(child, "id", None) == "selected-rows-display" for child in getattr(c, "children", []) or []))
        assert "max-height" not in panel.style


RATINGS = ["Align", "BOLD", "CompCor", "Corr", "Final", "Norm", "SDC", "SurfRecon", "T1mask", "Variance"]


def example_runs():
    return read_csv_exact(EXAMPLES / "df_final.csv", dtype={"ID": str, "session": str})


def shown_parts(dashboard):
    sections = {c.id: c for c in layout_components(dashboard) if isinstance(c.id, str) and c.id.endswith("-section")}
    return {name.removesuffix("-section") for name, c in sections.items() if c.style.get("display") != "none"}


class TestRatingFilters:

    def test_each_offers_only_the_ratings_in_its_column(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002", "003"], "session": ["01"] * 3, "run": [1, 1, 1],
                           "fd_mean": [0.1] * 3, "Final": ["good", "bad", "good"], "SDC": ["good", None, "other"]})
        dashboard = make_dashboard(FMRIPrepDashboard, df, tmp_path)
        named = {c.id: c for c in layout_components(dashboard) if isinstance(c.id, str)}
        assert [o["value"] for o in named["Final_dropdown"].options] == ["good", "bad"]
        assert [o["value"] for o in named["SDC_dropdown"].options] == ["good", "other", "NA"]
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "002", "003"]


class TestPlotParts:
    """A part of the Plots tab with nothing to show is hidden."""

    def test_ratings_and_metrics_show_every_part(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, example_runs(), tmp_path)
        assert shown_parts(dashboard) == {"heatmap", "quantitative", "qualitative", "lollipop"}

    def test_ratings_only_show_the_ratings_heatmap(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, example_runs()[["ID", "session", "run"] + RATINGS], tmp_path)
        assert shown_parts(dashboard) == {"heatmap", "qualitative"}
        assert dashboard.metrics == [] and len(shown_ids(dashboard, *layout_values(dashboard))) == 15

    def test_metrics_only_show_no_ratings_heatmap_or_filter(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, example_runs().drop(columns=RATINGS), tmp_path)
        assert shown_parts(dashboard) == {"heatmap", "quantitative", "lollipop"}
        assert dashboard.rating_columns() == [] and layout_values(dashboard)[2] == []

    def test_the_metrics_heatmap_appears_once_a_threshold_is_saved(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {}}}), encoding="utf-8")
        dashboard = make_dashboard(FMRIPrepDashboard, example_runs().drop(columns=RATINGS), tmp_path, config=config)
        assert shown_parts(dashboard) == {"lollipop"}

        rows = [{**config_rows(dashboard.config.metrics)[0], "bad-op": ">=", "bad-value": 0.3}]
        assert dashboard.settings.save(rows, version=0)[1]
        assert shown_parts(dashboard) == {"heatmap", "quantitative", "lollipop"}


class TestCustomDashboard:
    """Ratings, metrics and the default settings come from the values in the table."""

    def test_ratings_only(self, tmp_path):
        df = example_runs()[["ID", "session", "run"] + RATINGS]
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        assert dashboard.metrics == [] and dashboard.rating_columns() == RATINGS
        assert shown_parts(dashboard) == {"heatmap", "qualitative"}
        labels = [c.children for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Label"]
        assert labels == RATINGS
        assert len(shown_ids(dashboard, *layout_values(dashboard))) == 15

    def test_metrics_only_are_all_in_the_sidebar_without_thresholds(self, tmp_path):
        df = example_runs().drop(columns=RATINGS)
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        numeric = [c for c in df.columns if c not in ("ID", "session", "run", "task")]
        assert [m.column for m in dashboard.metrics] == numeric and not any(m.rated for m in dashboard.metrics)
        assert [m.label for m in dashboard.metrics] == numeric
        assert dashboard.config.table_columns == ("task",)
        assert shown_parts(dashboard) == {"lollipop"}
        assert len(shown_ids(dashboard, *layout_values(dashboard))) == 15

    def test_without_other_the_filter_offers_good_and_bad(self, tmp_path):
        df = example_runs()[["ID", "session", "run"] + RATINGS].replace("other", "bad")
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        dropdown = next(c for c in layout_components(dashboard) if c.id == "Final_dropdown")
        assert [o["value"] for o in dropdown.options] == ["good", "bad"]

    def test_pass_and_fail_are_shown_in_the_table_only(self, tmp_path):
        df = example_runs()[["ID", "session", "run"] + RATINGS]
        df["Final"] = df["Final"].map({"good": "pass", "other": "fail", "bad": "fail"})
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        assert "Final" not in dashboard.rating_columns() and dashboard.config.table_columns == ("Final",)
        assert "Final" in dashboard.table_column_ids()
        assert not any(c.id == "Final_dropdown" for c in layout_components(dashboard))
        assert len(shown_ids(dashboard, *layout_values(dashboard))) == 15

    def test_ratings_in_any_case_are_filtered_as_lower_case(self, tmp_path):
        df = pd.DataFrame({"ID": ["001", "002", "003"], "Final": [" Good", "BAD", None]})
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        ranges, statuses, ratings = layout_values(dashboard)
        assert ratings == [["good", "bad", "NA"]]
        assert shown_ids(dashboard, ranges, statuses, [["good"]]) == ["001"]

    @pytest.mark.parametrize("keys,group_by", [
        (["session", "run"], ["session", "run"]), (["session"], "session"), (["run"], "run"), ([], None)])
    def test_panels_follow_the_session_and_run_columns(self, tmp_path, keys, group_by):
        df = example_runs()[["ID"] + keys + ["fd_mean"]].drop_duplicates(["ID"] + keys)
        assert make_dashboard(CustomDashboard, df, tmp_path).GROUP_BY == group_by

    def test_use_defaults_and_saving_start_from_the_data(self, tmp_path):
        config = tmp_path / "custom_config.json"
        df = example_runs().drop(columns=RATINGS)[["ID", "session", "run", "task", "fd_mean", "fd_perc"]]
        dashboard = make_dashboard(CustomDashboard, df, tmp_path, config=config)
        assert dashboard.config_path is None and "starting from the default" in dashboard.config_source()
        tab = dashboard.settings
        assert [r["key"] for r in tab.edit([], "thr-defaults", 1, None)] == ["fd_mean", "fd_perc"]
        assert tab.edit_table([], "thr-defaults", None, []) == ["task"]

        rows = [{**config_rows(dashboard.config.metrics)[0], "bad-op": ">=", "bad-value": 0.3}]
        assert tab.save(rows, version=0, table=["task"])[1]
        assert json.loads(config.read_text(encoding="utf-8")) == {
            "metrics": {"fd_mean": {"label": "fd_mean", "bad": ">= 0.3"}}, "table_columns": ["task"]}
        assert shown_parts(dashboard) == {"heatmap", "quantitative", "lollipop"}

        reopened = make_dashboard(CustomDashboard, df, tmp_path, config=config)
        assert reopened.config_path == config and [m.column for m in reopened.metrics] == ["fd_mean"]

    def test_plots_draw_a_participant_without_runs(self, tmp_path):
        df = pd.concat([example_runs()[["ID", "session", "run", "fd_mean", "Final"]],
                        pd.DataFrame({"ID": ["099"], "fd_mean": [0.1]})], ignore_index=True)
        dashboard = make_dashboard(CustomDashboard, df, tmp_path)
        heatmaps = dash_call(dashboard, "quantitative-heatmap.figure",
                             {("filtered-rows", "data"): list(range(16)), ("main-tabs", "value"): "plots-tab"},
                             "filtered-rows.data")
        lollipop = dash_call(dashboard, "lollipop-chart.figure", {("main-tabs", "value"): "plots-tab"},
                             "main-tabs.value")
        assert heatmaps.status_code == 200 and lollipop.status_code == 200

    @pytest.mark.parametrize("task,name", [("rest", "rest_MRI_QC_subj.csv"), (None, "MRI_QC_subj.csv")])
    def test_the_download_is_named_after_the_task_if_given(self, tmp_path, task, name):
        data_file = tmp_path / "df_final.csv"
        precise_runs().to_csv(data_file, index=False)
        dashboard = CustomDashboard(CustomPipeline.from_saved_data(data_file), task=task)
        resp = dash_call(dashboard, "download-dataframe-csv.data",
                         {("download-button", "n_clicks"): 1, ("datatable", "selectedRows"): dashboard.table_records([0]),
                          ("filtered-rows", "data"): [0, 1, 2]}, "download-button.n_clicks")
        assert resp.get_json()["response"]["download-dataframe-csv"]["data"]["filename"] == name
