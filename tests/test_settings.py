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
from fMRI_QCtoolkit.dashboard.settings import (DOWNLOAD_IDLE_STYLE, DOWNLOAD_STYLE, FIELDS, NOTHING_TO_SAVE,
                                               SAVE_IDLE_STYLE, SAVE_STYLE, config_rows, form_raw, form_rows, new_row,
                                               row_entry)
from tests.dashboard_helpers import (afni_runs, dash_call, layout_components, layout_values, make_dashboard,
                                     shown_ids)


def fmriprep_runs():
    return pd.DataFrame({"ID": ["001", "002", "003", "004"], "session": ["01"] * 4, "run": [1] * 4,
                         "fd_perc": [5.0, 16.0, 25.0, np.nan], "fd_mean": [0.1, 0.1, 0.1, 0.1],
                         "efc": [0.5, 0.6, 0.7, 0.8], "task": ["rest"] * 4, "Final": ["good"] * 4})


def rows_of(dashboard):
    return config_rows(dashboard.config.metrics)


def row(rows, key):
    return next(r for r in rows if r["key"] == key)


def chip_texts(cell):
    return [c.children if isinstance(c.children, str) else c.children[0].children for c in cell.children]


def range_texts(cell):
    return [c.children[1] for c in cell.children if isinstance(c.children, list) and len(c.children) > 1]


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
        assert form_raw(config_rows(config.metrics)) == json.loads(default_config_path("afni").read_text(encoding="utf-8"))

    def test_an_empty_label_falls_back_to_the_column_name(self):
        assert row_entry({**new_row("efc"), "label": "  "}) == {}

    @pytest.mark.parametrize("fields,otherwise", [
        ({"good-op": "<=", "good-value": 15}, None),
        ({"good-op": "<=", "good-value": 15, "otherwise": "other"}, None),
        ({"good-op": "<=", "good-value": 15, "otherwise": "bad"}, "bad"),
        ({"otherwise": "good"}, None),
        ({"otherwise": "other"}, "other"),
    ])
    def test_otherwise_is_written_only_where_it_differs_from_the_default(self, fields, otherwise):
        assert row_entry({**new_row("efc"), **fields}).get("otherwise") == otherwise

    def test_a_number_without_an_operator_is_kept_for_the_check_to_reject(self):
        assert row_entry({**new_row("efc"), "bad-value": 0.3}) == {"label": "efc", "bad": "0.3"}

    @pytest.mark.parametrize("typed,read", [
        ("18", 18.0), (" 0.25 ", 0.25), ("1e-3", 0.001), ("", None), ("  ", None), (None, None),
        ("abc", "abc"), ("1,5", "1,5"), ("inf", "inf"), ("nan", "nan"),
    ])
    def test_number_boxes_are_read_as_numbers_or_kept_as_typed(self, typed, read):
        (form,) = form_rows(["efc"], *[[typed if f in ("good-value", "bad-value", "step") else None] for f in FIELDS])
        assert (form["good-value"], form["bad-value"], form["step"]) == (read, read, read)

    @pytest.mark.parametrize("field,typed,message", [
        ("good-value", "abc", "metrics.efc.good: '<= abc' is not a rule"),
        ("good-value", "inf", "metrics.efc.good: '<= inf' is not a rule"),
        ("step", "abc", "metrics.efc.step must be a positive number"),
    ])
    def test_text_that_is_not_a_number_is_a_row_error(self, tmp_path, field, typed, message):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        typed_in = {**dict.fromkeys(FIELDS), "label": "efc", "good-op": "<=", "good-value": "0.6", field: typed}
        (form,) = form_rows(["efc"], *[[typed_in[f]] for f in FIELDS])
        assert dashboard.settings.preview([form])['errors'][0].startswith(message)


class TestPreview:

    @pytest.mark.parametrize("entry", [
        {"label": " FD ", "good": "<= 15"},
        {"label": "", "good": "<= 15"},
        {"label": "FD", "good": "<= 15", "otherwise": "other"},
        {"label": "FD", "bad": "> 20", "otherwise": "good"},
    ])
    def test_an_untouched_form_has_no_unsaved_changes(self, saved_to, entry):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_perc": entry}})
        shown = dashboard.settings.preview(rows_of(dashboard))
        assert (shown['unsaved'], shown['save_style']) == ("", SAVE_IDLE_STYLE)

    def test_counts_per_status(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        shown = dashboard.settings.preview(rows_of(dashboard))
        cells, errors = shown['counts'], shown['errors']
        keys = [r["key"] for r in rows_of(dashboard)]
        assert chip_texts(cells[keys.index("fd_perc")]) == ["good 1", "other 1", "bad 1", "NA 1"]
        assert cells[keys.index("tsnr")].children == "not in the data"
        assert errors == [None] * len(keys)

    def test_each_level_shows_its_runs_and_the_values_it_covers(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard) + [{**new_row("efc"), "bad-op": ">=", "bad-value": 0.7, "otherwise": "other"}]
        cells = dict(zip([r["key"] for r in rows], dashboard.settings.preview(rows)['counts']))
        assert chip_texts(cells["fd_perc"]) == ["good 1", "other 1", "bad 1", "NA 1"]
        assert range_texts(cells["fd_perc"]) == ["x ≤ 15", "15 < x ≤ 20", "x > 20"]
        assert (chip_texts(cells["efc"]), range_texts(cells["efc"])) == (
            ["other 2", "bad 2", "NA 0"], ["x < 0.7", "x ≥ 0.7"])

    def test_otherwise_shows_in_gray_the_level_the_rules_give(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard) + [{**new_row("efc"), "good-op": "<", "good-value": 0.6}]
        assert all(r["otherwise"] is None for r in rows)
        defaults = dict(zip([r["key"] for r in rows], dashboard.settings.preview(rows)['rest_defaults']))
        assert (defaults["fd_perc"], defaults["tsnr"], defaults["efc"]) == ("other", "good", "other")

    def test_a_metric_rated_other_throughout_is_counted(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard) + [{**new_row("efc"), "otherwise": "other"}]
        assert chip_texts(dashboard.settings.preview(rows)['counts'][-1]) == ["other 4", "NA 0"]

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
        row(rows, "fd_perc").update({"good-value": 8, "bad-value": 10})
        summary = dashboard.settings.preview(rows)['summary']
        assert summary == "Runs shown when the dashboard opens: 2 of 4 (now 3)."

    def test_a_bad_row_shows_the_config_check_message(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_mean").update({"good-value": 0.5, "bad-value": 0.3})
        row(rows, "fd_perc").update({"bad-op": None})
        shown = dashboard.settings.preview(rows)
        errors, summary = shown['errors'], shown['summary']
        keys = [r["key"] for r in rows]
        assert "overlap" in errors[keys.index("fd_mean")]
        assert errors[keys.index("fd_perc")].startswith("metrics.fd_perc.bad: '20' is not a rule")
        assert summary.endswith("Rows with errors are left out.")
        assert shown['save_off'] and shown['unsaved'] == "Unsaved changes"
        assert shown['download_style'] == DOWNLOAD_IDLE_STYLE

    def test_save_is_off_without_a_config_file(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_perc").update({"good-value": 8, "bad-value": 10})
        shown = dashboard.settings.preview(rows)
        assert shown['save_off'] and shown['unsaved'] == "Unsaved changes"
        assert shown['download_style'] == DOWNLOAD_STYLE

    def test_save_is_faded_until_something_changes_but_always_takes_a_click(self, saved_to):
        # A click right after typing sends the value first, while the button still looks unchanged
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        rows = rows_of(dashboard)
        shown = dashboard.settings.preview(rows)
        assert (shown['save_off'], shown['save_style'], shown['unsaved']) == (False, SAVE_IDLE_STYLE, "")
        row(rows, "fd_mean")["label"] = "Mean FD"
        shown = dashboard.settings.preview(rows)
        assert (shown['save_off'], shown['save_style'], shown['unsaved']) == (False, SAVE_STYLE, "Unsaved changes")

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
        assert self.keys(rows)[-2:] == ["efc", "aqi"]
        rows = tab.edit(rows, {"type": "thr-down", "key": "fd_perc"}, 1, None)
        assert self.keys(rows)[:2] == ["fd_mean", "fd_perc"]
        rows = tab.edit(rows, {"type": "thr-delete", "key": "efc"}, 1, None)
        assert "efc" not in self.keys(rows)

    def test_newly_drawn_buttons_and_edges_change_nothing(self, tmp_path):
        tab = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path).settings
        rows = rows_of(tab.dashboard)
        for trigger, clicked in [({"type": "thr-delete", "key": "fd_perc"}, 0),
                                 ({"type": "thr-up", "key": "fd_perc"}, 1),
                                 ({"type": "thr-down", "key": "aqi"}, 1)]:
            with pytest.raises(PreventUpdate):
                tab.edit(rows, trigger, clicked, None)

    def test_discard_and_defaults(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_mean": {"bad": "> 1"}}})
        tab = dashboard.settings
        assert self.keys(tab.edit([new_row("efc")], "thr-discard", 1, None)) == ["fd_mean"]
        defaults = tab.edit([], "thr-defaults", 1, None)
        assert defaults == config_rows(load_config(default_config_path("fmriprep")).metrics)


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
        assert dashboard.table_column_ids()[-2:] == ["efc", "Final"]

    def test_a_folder_that_cannot_be_written_points_to_config_and_download(self, saved_to, monkeypatch):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())

        def refuse(*args):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("fMRI_QCtoolkit.dashboard.settings.save_config", refuse)
        message, saved = dashboard.settings.save(rows_of(dashboard), version=0)
        assert not saved
        assert all(part in message for part in ("Permission denied", "--config FILE", "Download config"))
        assert dashboard.config_version == 0

    def test_saving_otherwise_rates_the_rest_with_it(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_mean": {}}})
        rows = rows_of(dashboard) + [{**new_row("efc"), "good-op": "<", "good-value": 0.65, "otherwise": "bad"}]
        assert dashboard.settings.save(rows, version=0)[1]
        assert json.loads(path.read_text(encoding="utf-8"))["metrics"]["efc"] == {
            "label": "efc", "good": "< 0.65", "otherwise": "bad"}
        assert dashboard.status["efc"].tolist() == ["good", "good", "bad", "bad"]

    def test_the_previous_file_is_kept_as_bak(self, saved_to):
        original = {"metrics": {"fd_mean": {"bad": "> 1"}}}
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), original)
        rows = rows_of(dashboard)
        rows[0]["bad-value"] = 2
        assert dashboard.settings.save(rows, version=0)[1]
        assert json.loads(path.with_name("thresholds.json.bak").read_text(encoding="utf-8")) == original
        assert load_config(path).metrics["fd_mean"].rules == {"bad": (">", 2.0)}

    def test_the_page_built_after_a_save_shows_the_new_thresholds(self, saved_to):
        dashboard, _ = saved_to(AFNIDashboard, afni_runs())
        rows = rows_of(dashboard)
        row(rows, "cens_frac")["bad-value"] = 0.3
        dashboard.settings.save(rows, version=0)
        lines = [c.children for c in dashboard.build_layout()._traverse() if type(c).__name__ == "Li"]
        assert "Censor Fraction: good < 0.15, bad ≥ 0.3" in lines
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
        assert load_config(path).metrics["fd_mean"].label == "Mean FD"

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

    def test_saving_unchanged_settings_leaves_the_file_and_its_backup_alone(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_mean": {"bad": "> 1"}}})
        assert dashboard.settings.save(rows_of(dashboard), version=0) == (NOTHING_TO_SAVE, False)
        assert sorted(p.name for p in path.parent.iterdir()) == ["thresholds.json"]
        assert dashboard.config_version == 0

    def test_moving_a_row_is_a_change_that_save_writes(self, saved_to):
        original = {"metrics": {"fd_mean": {"bad": "> 1"}, "fd_perc": {"bad": "> 20"}}}
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), original)
        rows = rows_of(dashboard)[::-1]
        shown = dashboard.settings.preview(rows)
        assert (shown['save_style'], shown['unsaved']) == (SAVE_STYLE, "Unsaved changes")
        assert dashboard.settings.save(rows, version=0)[1]
        assert list(json.loads(path.read_text(encoding="utf-8"))["metrics"]) == ["fd_perc", "fd_mean"]

    def test_saving_an_untouched_form_leaves_table_columns_in_their_hand_written_order(self, saved_to):
        original = {"metrics": {"fd_mean": {"bad": "> 1"}}, "table_columns": ["task", "efc"]}
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), original)
        table = list(dashboard.config.table_columns)
        assert dashboard.settings.preview(rows_of(dashboard), table)['unsaved'] == ""
        assert dashboard.settings.save(rows_of(dashboard), 0, table) == (NOTHING_TO_SAVE, False)
        assert sorted(p.name for p in path.parent.iterdir()) == ["thresholds.json"]

    def test_saving_an_untouched_form_creates_the_missing_file(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        assert dashboard.settings.save(rows_of(dashboard), version=0)[1]
        assert load_config(path) == dashboard.config


class TestTableOnlyColumns:

    def test_on_offer_are_the_columns_not_ids_ratings_or_metrics(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        assert dashboard.settings.preview(rows_of(dashboard))['table_options'] == ["efc", "task"]
        assert dashboard.settings.preview(rows_of(dashboard) + [new_row("efc")])['table_options'] == ["task"]

    def test_picking_one_is_an_unsaved_change(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        shown = dashboard.settings.preview(rows_of(dashboard), ["efc"])
        assert (shown['save_off'], shown['unsaved'], shown['table_error']) == (False, "Unsaved changes", None)

    def test_one_that_is_also_a_metric_is_refused(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        shown = dashboard.settings.preview(rows_of(dashboard), ["fd_mean"])
        assert "['fd_mean'] already in metrics" in shown['table_error']
        assert (shown['save_style'], shown['download_style']) == (SAVE_IDLE_STYLE, DOWNLOAD_IDLE_STYLE)

    def test_adding_it_as_a_metric_takes_it_out_of_the_table_only_list(self, tmp_path):
        tab = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path).settings
        assert tab.edit_table(["efc", "task"], "thr-add", "efc", ["fd_mean", "efc"]) == ["task"]

    def test_select_all_and_clear(self, tmp_path):
        tab = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path).settings
        assert tab.edit_table([], "thr-table-all", None, ["fd_mean"]) == ["fd_perc", "efc", "task"]
        assert tab.edit_table(["efc"], "thr-table-clear", None, ["fd_mean"]) == []

    def test_discard_and_defaults(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs(),
                                {"metrics": {"fd_mean": {"bad": "> 1"}}, "table_columns": ["efc"]})
        tab = dashboard.settings
        assert tab.edit_table([], "thr-discard", None, ["fd_mean"]) == ["efc"]
        assert tab.edit_table(["efc"], "thr-defaults", None, ["fd_mean"]) == []

    def test_the_order_they_are_picked_in_is_not_a_change(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs(),
                                {"metrics": {"fd_mean": {"bad": "> 1"}}, "table_columns": ["efc", "task"]})
        assert dashboard.settings.preview(rows_of(dashboard), ["task", "efc"])['unsaved'] == ""

    def test_saving_writes_them_in_data_order_and_the_table_shows_them_after_the_metrics(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs(), {"metrics": {"fd_mean": {"bad": "> 1"}}})

        message, saved = dashboard.settings.save(rows_of(dashboard), 0, ["task", "efc"])

        assert saved, message
        assert json.loads(path.read_text(encoding="utf-8"))["table_columns"] == ["efc", "task"]
        assert dashboard.table_column_ids() == ["ID", "session", "run", "fd_mean", "efc", "task", "Final"]
        assert shown_ids(dashboard, *layout_values(dashboard)) == ["001", "002", "003", "004"]

    def test_the_downloaded_file_has_them(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        _, text = dashboard.settings.config_file(rows_of(dashboard), ["efc"])
        assert parse_config(json.loads(text)).table_columns == ("efc",)


class TestDownloading:

    def test_the_file_is_the_form_laid_out_like_the_default(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        rows = rows_of(dashboard)
        row(rows, "fd_perc")["bad-value"] = 30
        name, text = dashboard.settings.config_file(rows)
        assert name == "fmriprep_config.json"
        assert text == dump_config(form_raw(rows))
        assert parse_config(json.loads(text)).metrics["fd_perc"].rules["bad"] == (">", 30.0)

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

    def test_the_header_and_every_row_have_the_ten_cells_the_layout_places(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        grids = [c for c in dashboard.build_layout()._traverse() if getattr(c, "className", None) == "thr-grid"]
        assert len(grids) == 1 + len(rows_of(dashboard))
        assert all(len(grid.children) == 10 for grid in grids)

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
        assert parse_config(json.loads(sent["content"])).metrics["fd_perc"].rules["bad"] == (">", 30.0)

    def test_the_download_button_says_why_an_invalid_form_gives_no_file(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-download.data",
                         {("thr-download-button", "n_clicks"): 1, (sid("thr-bad-value", "fd_mean"), "value"): 0.1},
                         "thr-download-button.n_clicks")
        response = resp.get_json()["response"]
        assert "thr-download" not in response
        assert "Not downloaded: fmriprep_config.json: metrics.fd_mean" in json.dumps(response["thr-message"])

    def test_the_save_button_writes_the_form_to_the_config_path(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        resp = dash_call(dashboard, "thr-saved.data",
                         {("thr-save", "n_clicks"): 1, (sid("thr-bad-value", "fd_perc"), "value"): 30},
                         "thr-save.n_clicks")
        assert resp.status_code == 200
        assert resp.get_json()["response"]["thr-saved"]["data"] == 1
        assert load_config(path).metrics["fd_perc"].rules["bad"] == (">", 30.0)

    def test_the_preview_answers_for_every_row(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-summary.children", {(sid("thr-bad-op", "fd_perc"), "value"): None},
                         sid("thr-bad-op", "fd_perc") + ".value")
        response = resp.get_json()["response"]
        counts = {json.loads(k)["key"]: v["children"] for k, v in response.items() if k.startswith("{") and "counts" in k}
        assert set(counts) == {r["key"] for r in rows_of(dashboard)}
        assert response["thr-summary"]["children"].startswith("Runs shown when the dashboard opens: 4 of 4")

    def test_adding_a_row_redraws_the_rows(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-rows.children", {("thr-add", "value"): "efc"}, "thr-add.value")
        response = resp.get_json()["response"]
        assert len(response["thr-rows"]["children"]) == len(rows_of(dashboard)) + 1
        assert response["thr-add"]["value"] is None

    def test_adding_a_table_only_column_as_a_metric_moves_it(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-rows.children", {("thr-add", "value"): "efc", ("thr-table", "value"): ["efc"]},
                         "thr-add.value")
        assert resp.get_json()["response"]["thr-table"]["value"] == []

    def test_select_all_ticks_every_column_on_offer(self, tmp_path):
        dashboard = make_dashboard(FMRIPrepDashboard, fmriprep_runs(), tmp_path)
        resp = dash_call(dashboard, "thr-rows.children", {("thr-table-all", "n_clicks"): 1}, "thr-table-all.n_clicks")
        assert resp.get_json()["response"] == {"thr-table": {"value": ["efc", "task"]}}

    def test_picking_a_table_only_column_updates_the_preview(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        resp = dash_call(dashboard, "thr-summary.children", {("thr-table", "value"): ["efc"]}, "thr-table.value")
        response = resp.get_json()["response"]
        assert response["thr-table"]["options"] == ["efc", "task"]
        assert response["thr-save"]["disabled"] is False
        assert response["thr-unsaved"]["children"] == "Unsaved changes"

    def test_the_save_button_writes_the_table_only_columns(self, saved_to):
        dashboard, path = saved_to(FMRIPrepDashboard, fmriprep_runs())
        resp = dash_call(dashboard, "thr-saved.data",
                         {("thr-save", "n_clicks"): 1, ("thr-table", "value"): ["efc"]}, "thr-save.n_clicks")
        assert resp.get_json()["response"]["thr-saved"]["data"] == 1
        assert load_config(path).table_columns == ("efc",)

    def test_a_page_built_before_a_save_still_filters(self, saved_to):
        dashboard, _ = saved_to(FMRIPrepDashboard, fmriprep_runs())
        old_page = layout_components(dashboard)
        rows = rows_of(dashboard) + [{**new_row("efc"), "bad-op": ">=", "bad-value": 0.7}]
        dashboard.settings.save(rows, version=0)

        table = dash_call(dashboard, "datatable.rowData", {}, stringify_id({"type": "metric-range", "column": "fd_mean"})
                          + ".value", comps=old_page).get_json()["response"]
        assert [r["ID"] for r in table["datatable"]["rowData"]] == ["001", "002"]

        banner = dash_call(dashboard, "stale-banner.children", {}, "main-tabs.value", comps=old_page)
        assert "Reload the page" in json.dumps(banner.get_json()["response"])
