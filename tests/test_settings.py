"""
Tests for the Settings tab: the form, its preview, editing the rows, saving to the --config file and downloading.
"""

import json

import numpy as np
import pandas as pd
import pytest
from dash._utils import stringify_id
from dash.exceptions import PreventUpdate

from fMRI_QCtoolkit.dashboard.afni_app import AFNIDashboard
from fMRI_QCtoolkit.dashboard.config import ConfigError
from fMRI_QCtoolkit.dashboard.config import default_config_path, dump_config, load_config, parse_config
from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard
from fMRI_QCtoolkit.dashboard.settings import config_rows, form_raw, new_row, row_entry
from tests.dashboard_helpers import (afni_runs, dash_call, layout_components, layout_values, make_dashboard,
                                     shown_ids)


def fmriprep_runs():
    return pd.DataFrame({"ID": ["001", "002", "003", "004"], "session": ["01"] * 4, "run": [1] * 4,
                         "fd_perc": [5.0, 16.0, 25.0, np.nan], "fd_mean": [0.1, 0.1, 0.1, 0.1],
                         "efc": [0.5, 0.6, 0.7, 0.8], "modality": ["rest"] * 4, "Final": ["good"] * 4})


def rows_of(dashboard):
    return config_rows(dashboard.config)


def row(rows, key):
    return next(r for r in rows if r["key"] == key)


def chip_texts(cell):
    return [c.children for c in cell.children]


@pytest.fixture
def saved_to(tmp_path):
    def build(cls, df, config=None):
        path = tmp_path / "mine" / "thresholds.json"
        path.parent.mkdir()
        if config is not None:
            path.write_text(json.dumps(config), encoding="utf-8")
        return make_dashboard(cls, df, tmp_path, config=path), path
    return build


class TestFormEntries:

    def test_rows_read_back_as_the_config(self):
        config = load_config(default_config_path("afni"))
        assert form_raw(config_rows(config)) == json.loads(default_config_path("afni").read_text(encoding="utf-8"))

    def test_an_empty_label_falls_back_to_the_column_name(self):
        assert row_entry({**new_row("efc"), "label": "  "}) == {}

    def test_a_number_without_an_operator_is_kept_for_the_check_to_reject(self):
        assert row_entry({**new_row("efc"), "bad-value": 0.3}) == {"label": "efc", "bad": "0.3"}


class TestPreview:

    def test_counts_per_status(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        shown = dashboard.settings.preview(rows_of(dashboard))
        cells, errors = shown['counts'], shown['errors']
        keys = [r["key"] for r in rows_of(dashboard)]
        assert chip_texts(cells[keys.index("fd_perc")]) == ["good 1", "other 1", "bad 1", "NA 1"]
        assert cells[keys.index("tsnr")].children == "not in the data"
        assert errors == [None] * len(keys)

    def test_an_unrated_metric_says_so(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard) + [new_row("efc")]
        cells = dashboard.settings.preview(rows)['counts']
        assert cells[-1].children == "no thresholds"

    def test_a_pattern_counts_the_worst_status_of_its_columns(self, tmp_path):
        df = afni_runs()
        df["frac_TRs_cens_2"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, np.nan]
        dashboard = make_dashboard(AFNIDashboard, df, tmp_path)
        rows = rows_of(dashboard)
        cells = dashboard.settings.preview(rows)['counts']
        cell = cells[[r["key"] for r in rows].index("frac_TRs_cens_*")]
        assert chip_texts(cell) == ["good 6", "bad 2", "NA 0", "worst of 2 columns"]

    def test_summary_counts_the_runs_the_new_thresholds_would_show(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_perc").update({"other-value": 8, "bad-value": 10})
        summary = dashboard.settings.preview(rows)['summary']
        assert summary == "With these thresholds, 2 of 4 runs are shown when the dashboard opens (now 3)."

    def test_a_bad_row_shows_the_config_check_message(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_mean").update({"other-value": 0.5, "bad-value": 0.3})
        row(rows, "fd_perc").update({"bad-op": None})
        shown = dashboard.settings.preview(rows)
        errors, summary = shown['errors'], shown['summary']
        keys = [r["key"] for r in rows]
        assert "bad is looser than other" in errors[keys.index("fd_mean")]
        assert errors[keys.index("fd_perc")].startswith("metrics.fd_perc.bad: '20' is not a rule")
        assert summary.endswith("Rows with an error are left out until they are fixed.")
        assert shown['save_off'] and shown['download_off'] and shown['unsaved'] == "Unsaved changes"

    def test_save_is_off_without_a_config_file(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_perc").update({"other-value": 8, "bad-value": 10})
        shown = dashboard.settings.preview(rows)
        assert shown['save_off'] and not shown['download_off'] and shown['unsaved'] == "Unsaved changes"

    def test_save_is_on_only_when_something_changed(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        rows = rows_of(dashboard)
        shown = dashboard.settings.preview(rows)
        assert (shown['save_off'], shown['unsaved']) == (True, "")
        row(rows, "fd_mean")["label"] = "Mean FD"
        shown = dashboard.settings.preview(rows)
        assert (shown['save_off'], shown['unsaved']) == (False, "Unsaved changes")

    def test_columns_on_offer_are_numeric_and_not_yet_covered(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        assert dashboard.settings.preview(rows_of(dashboard))['options'] == ["efc"]
        assert dashboard.settings.preview(rows_of(dashboard) + [new_row("efc")])['options'] == []


class TestEditingRows:

    def keys(self, rows):
        return [r["key"] for r in rows]

    def test_add_move_and_remove(self, tmp_path):
        tab = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path).settings
        rows = tab.edit(rows_of(tab.dashboard), "thr-add", None, "efc")
        assert self.keys(rows)[-1] == "efc"
        rows = tab.edit(rows, {"type": "thr-up", "key": "efc"}, 1, None)
        assert self.keys(rows)[-2:] == ["efc", "seconds_per_run"]
        rows = tab.edit(rows, {"type": "thr-down", "key": "fd_perc"}, 1, None)
        assert self.keys(rows)[:2] == ["fd_mean", "fd_perc"]
        rows = tab.edit(rows, {"type": "thr-delete", "key": "efc"}, 1, None)
        assert "efc" not in self.keys(rows)

    def test_newly_drawn_buttons_and_edges_change_nothing(self, tmp_path):
        tab = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path).settings
        rows = rows_of(tab.dashboard)
        for trigger, clicked in [({"type": "thr-delete", "key": "fd_perc"}, 0),
                                 ({"type": "thr-up", "key": "fd_perc"}, 1),
                                 ({"type": "thr-down", "key": "seconds_per_run"}, 1)]:
            with pytest.raises(PreventUpdate):
                tab.edit(rows, trigger, clicked, None)

    def test_discard_and_defaults(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_mean": {"bad": "> 1"}}})
        tab = dashboard.settings
        assert self.keys(tab.edit([new_row("efc")], "thr-discard", 1, None)) == ["fd_mean"]
        defaults = tab.edit([], "thr-defaults", 1, None)
        assert defaults == config_rows(load_config(default_config_path("fmriprep")))


class TestSaving:

    def test_saving_writes_the_file_and_rates_the_runs_again(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        rows = rows_of(dashboard) + [{**new_row("efc"), "bad-op": ">=", "bad-value": 0.7}]

        message, saved = dashboard.settings.save(rows, version=0)

        assert saved, message
        assert json.loads(path.read_text(encoding="utf-8")) == form_raw(rows)
        assert not path.with_name("thresholds.json.bak").exists()
        assert dashboard.config_version == 1
        assert dashboard.status["efc"].tolist() == ["good", "good", "bad", "bad"]
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "002"]
        assert "efc" not in dashboard.hidden_columns()

    def test_the_previous_file_is_kept_as_bak(self, saved_to):
        original = {"metrics": {"fd_mean": {"bad": "> 1"}}}
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), original)
        rows = rows_of(dashboard)
        rows[0]["bad-value"] = 2
        assert dashboard.settings.save(rows, version=0)[1]
        assert json.loads(path.with_name("thresholds.json.bak").read_text(encoding="utf-8")) == original
        assert load_config(path)["fd_mean"].rules == {"bad": (">", 2.0)}

    def test_the_page_built_after_a_save_shows_the_new_thresholds(self, saved_to):
        dashboard, _ = saved_to(AFNIDashboard, afni_runs())
        rows = rows_of(dashboard)
        row(rows, "cens_frac")["bad-value"] = 0.3
        dashboard.settings.save(rows, version=0)
        lines = [c.children for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Li"]
        assert "Censor Fraction: other ≥ 0.15, bad ≥ 0.3" in lines
        store = next(c for c in layout_components(dashboard) if c.id == "config-version")
        assert store.data == 1

    def test_a_page_older_than_the_last_save_cannot_save(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        rows = rows_of(dashboard)
        row(rows, "fd_mean")["label"] = "Mean FD"
        assert dashboard.settings.save(rows, version=0)[1]
        row(rows, "fd_mean")["label"] = "Other tab"
        message, saved = dashboard.settings.save(rows, version=0)
        assert not saved and "Reload the page" in message
        assert load_config(path)["fd_mean"].label == "Mean FD"

    def test_nothing_is_saved_without_a_config_file(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        message, saved = dashboard.settings.save(rows_of(dashboard), version=0)
        assert not saved and "--config" in message
        assert dashboard.config_version == 0

    def test_an_invalid_form_leaves_the_file_alone(self, saved_to):
        original = {"metrics": {"fd_mean": {"bad": "> 1"}}}
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), original)
        message, saved = dashboard.settings.save([], version=0)
        assert not saved and "'metrics' must be a non-empty object" in message
        assert json.loads(path.read_text(encoding="utf-8")) == original
        assert sorted(p.name for p in path.parent.iterdir()) == ["thresholds.json"]


class TestDownloading:

    def test_the_file_is_the_form_laid_out_like_the_default(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_perc")["bad-value"] = 30
        name, text = dashboard.settings.config_file(rows)
        assert name == "fmriprep_config.json"
        assert text == dump_config(form_raw(rows))
        assert parse_config(json.loads(text))["fd_perc"].rules["bad"] == (">", 30.0)

    def test_the_file_takes_the_config_file_name(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        assert dashboard.settings.config_file(rows_of(dashboard))[0] == path.name
        assert not path.exists()

    def test_an_invalid_form_gives_no_file(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_mean")["bad-value"] = 0.1
        with pytest.raises(ConfigError):
            dashboard.settings.config_file(rows)


def sid(kind, key):
    return stringify_id({"type": kind, "key": key})


class TestThroughDash:
    """The tab's callbacks driven by Dash requests, as the browser sends them."""

    def test_the_tab_is_called_settings(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        tabs = [c.label for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Tab"]
        assert tabs == ["Table", "Plots", "Settings"]

    def test_the_download_button_sends_the_form(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-download.data",
                         {("thr-download-button", "n_clicks"): 1, (sid("thr-bad-value", "fd_perc"), "value"): 30},
                         "thr-download-button.n_clicks")
        sent = resp.get_json()["response"]["thr-download"]["data"]
        assert sent["filename"] == "fmriprep_config.json"
        assert parse_config(json.loads(sent["content"]))["fd_perc"].rules["bad"] == (">", 30.0)


    def test_the_save_button_writes_the_form_to_the_config_path(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        resp = dash_call(dashboard, "thr-message.children",
                         {("thr-save", "n_clicks"): 1, (sid("thr-bad-value", "fd_perc"), "value"): 30},
                         "thr-save.n_clicks")
        assert resp.status_code == 200
        assert resp.get_json()["response"]["thr-saved"]["data"] == 1
        assert load_config(path)["fd_perc"].rules["bad"] == (">", 30.0)

    def test_the_preview_answers_for_every_row(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-summary.children", {(sid("thr-bad-op", "fd_perc"), "value"): None},
                         sid("thr-bad-op", "fd_perc") + ".value")
        response = resp.get_json()["response"]
        counts = {json.loads(k)["key"]: v["children"] for k, v in response.items() if k.startswith("{") and "counts" in k}
        assert set(counts) == {r["key"] for r in rows_of(dashboard)}
        assert response["thr-summary"]["children"].startswith("With these thresholds, 4 of 4 runs")

    def test_adding_a_row_redraws_the_rows(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-rows.children", {("thr-add", "value"): "efc"}, "thr-add.value")
        response = resp.get_json()["response"]
        assert len(response["thr-rows"]["children"]) == len(rows_of(dashboard)) + 1
        assert response["thr-add"]["value"] is None

    def test_a_page_built_before_a_save_still_filters(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        old_page = layout_components(dashboard)
        rows = rows_of(dashboard) + [{**new_row("efc"), "bad-op": ">=", "bad-value": 0.7}]
        dashboard.settings.save(rows, version=0)

        resp = dash_call(dashboard, "datatable.data", {}, "select-all-button.n_clicks", comps=old_page)
        assert resp.status_code == 200
        table = dash_call(dashboard, "datatable.data", {}, stringify_id({"type": "metric-range", "column": "fd_mean"})
                          + ".value", comps=old_page).get_json()["response"]
        assert [r["ID"] for r in table["datatable"]["data"]] == ["001", "002"]

        banner = dash_call(dashboard, "stale-banner.children", {}, "main-tabs.value", comps=old_page)
        assert "Reload the page" in json.dumps(banner.get_json()["response"])
