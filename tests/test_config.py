import json

import pytest

from fMRI_QCtoolkit.dashboard.config import (
    ConfigError,
    default_config_path,
    load_config,
    parse_config,
    resolve_metrics,
)


def write_config(tmp_path, content):
    path = tmp_path / "my_config.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


class TestPackagedConfigs:

    def test_afni_entries_in_sidebar_order(self):
        config = load_config(default_config_path("afni"))
        assert list(config) == ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac",
                                "flip_guess", "GCOR", "frac_TRs_cens_*"]
        assert config["cens_frac"].label == "Censor Fraction"

    def test_fmriprep_colors_only_the_motion_metrics(self):
        config = load_config(default_config_path("fmriprep"))
        assert [key for key, metric in config.items() if metric.rules] == ["fd_perc", "fd_mean"]


class TestConfigErrors:

    @pytest.mark.parametrize("content,message", [
        ("{not json", "not valid JSON"),
        ({"quantitative_configs": []}, "1.x format"),
        ({"metrics": {}}, "non-empty object"),
        ({"metrics": {"x": {}}, "heatmap": []}, "unknown top-level field(s) ['heatmap']"),
        ({"metrics": {"cens_frac": {"lable": "C"}}}, "metrics.cens_frac: unknown field(s) ['lable']"),
        ({"metrics": {"cens_frac": {"bad": "=> 0.2"}}}, "metrics.cens_frac.bad: '=> 0.2' is not a rule"),
        ({"metrics": {"cens_frac": {"other": ">= 0.2", "bad": ">= 0.15"}}}, "are they swapped"),
        ({"metrics": {"DF_frac": {"other": "<= 0.7", "bad": "<= 0.8"}}}, "are they swapped"),
        ({"metrics": {"DF_frac": {"other": "<= 0.7", "bad": ">= 0.6"}}}, "opposite directions"),
        ({"metrics": {"x": {"step": 0}}}, "metrics.x.step must be a positive number"),
        ({"metrics": {"x": {"label": 3}}}, "metrics.x.label must be text"),
        ({"metrics": {"x": "GCOR"}}, "metrics.x must be an object"),
        ('{"metrics": {"x": {}, "x": {}}}', "duplicate key(s) ['x']"),
    ])
    def test_message_names_the_file_and_the_problem(self, tmp_path, content, message):
        path = write_config(tmp_path, content)
        with pytest.raises(ConfigError) as err:
            load_config(path)
        assert message in str(err.value)
        assert str(path) in str(err.value)

    def test_equality_rules_skip_the_order_check(self):
        config = parse_config({"metrics": {"code": {"other": "== 1", "bad": "== 2"}}})
        assert config["code"].rules == {"other": ("==", 1.0), "bad": ("==", 2.0)}

    def test_byte_order_mark_is_accepted(self, tmp_path):
        path = tmp_path / "bom.json"
        path.write_text('﻿{"metrics": {"aqi": {}}}', encoding="utf-8")
        assert list(load_config(path)) == ["aqi"]


class TestResolveMetrics:

    def test_follows_config_order_and_skips_absent_columns(self):
        config = parse_config({"metrics": {"b": {}, "a": {}, "zz": {}}})
        assert [m.column for m in resolve_metrics(config, ["a", "b", "c"])] == ["b", "a"]

    def test_label_defaults_to_the_column(self):
        assert parse_config({"metrics": {"aqi": {}}})["aqi"].label == "aqi"

    def test_star_expands_in_table_order(self):
        config = parse_config({"metrics": {"frac_TRs_cens_*": {"label": "Fraction TRs Censored",
                                                               "bad": ">= 0.2"}}})
        metrics = resolve_metrics(config, ["ID", "frac_TRs_cens_2", "frac_TRs_cens_1"])
        assert [(m.column, m.label, m.entry_label) for m in metrics] == [
            ("frac_TRs_cens_2", "frac_TRs_cens_2", "Fraction TRs Censored"),
            ("frac_TRs_cens_1", "frac_TRs_cens_1", "Fraction TRs Censored"),
        ]
        assert all(m.rules == {"bad": (">=", 0.2)} for m in metrics)

    def test_matching_is_case_sensitive(self):
        config = parse_config({"metrics": {"TSNR": {}, "gcor*": {}}})
        assert resolve_metrics(config, ["tsnr", "GCOR"]) == []

    def test_a_column_is_used_once(self):
        config = parse_config({"metrics": {"cens_frac": {"label": "A"}, "cens_*": {}}})
        resolved = resolve_metrics(config, ["cens_frac", "cens_mot"])
        assert [(m.column, m.label) for m in resolved] == [("cens_frac", "A"), ("cens_mot", "cens_mot")]
