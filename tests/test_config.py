import json

import pytest

from fMRI_QCtoolkit.dashboard.config import (
    ConfigError,
    config_to_raw,
    default_config_path,
    dump_config,
    load_config,
    parse_config,
    resolve_metrics,
    same_settings,
    save_config,
)


def write_config(tmp_path, content):
    path = tmp_path / "my_config.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


class TestPackagedConfigs:

    def test_afni_entries_in_sidebar_order(self):
        config = load_config(default_config_path("afni")).metrics
        assert list(config) == ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac",
                                "flip_guess", "GCOR", "frac_TRs_cens_*"]
        assert config["cens_frac"].label == "Censor Fraction"

    def test_fmriprep_colors_only_the_motion_metrics(self):
        config = load_config(default_config_path("fmriprep")).metrics
        assert [key for key, metric in config.items() if metric.rules] == ["fd_perc", "fd_mean"]


class TestConfigErrors:

    @pytest.mark.parametrize("content,message", [
        ("{not json", "not valid JSON"),
        ({"quantitative_configs": []}, "1.x format"),
        ({"metrics": {}}, "non-empty object"),
        ({"metrics": {"x": {}}, "heatmap": []}, "unknown top-level field(s) ['heatmap']"),
        ({"metrics": {"cens_frac": {"lable": "C"}}}, "metrics.cens_frac: unknown field(s) ['lable']"),
        ({"metrics": {"cens_frac": {"bad": "=> 0.2"}}}, "metrics.cens_frac.bad: '=> 0.2' is not a rule"),
        ({"metrics": {"cens_frac": {"good": "< 0.25", "bad": ">= 0.2"}}},
         "good (< 0.25) and bad (>= 0.2) overlap, so a value such as 0.2 would be both"),
        ({"metrics": {"DF_frac": {"good": "> 0.7", "bad": "> 0.8"}}}, "overlap"),
        ({"metrics": {"x": {"good": "!= 0", "bad": "> 5"}}}, "overlap"),
        ({"metrics": {"x": {"otherwise": "fine"}}}, "metrics.x.otherwise must be one of good, other, bad"),
        ({"metrics": {"DF_frac": {"other": "<= 0.7", "bad": "<= 0.6"}}},
         "'other' is no longer a field, since other is whatever is neither good nor bad; "
         "replace \"other\": \"<= 0.7\" with \"good\": \"> 0.7\""),
        ({"metrics": {"x": {"step": 0}}}, "metrics.x.step must be a positive number"),
        ({"metrics": {"x": {"label": 3}}}, "metrics.x.label must be text"),
        ({"metrics": {"x": "GCOR"}}, "metrics.x must be an object"),
        ('{"metrics": {"x": {}, "x": {}}}', "duplicate key(s) ['x']"),
        ({"metrics": {"x": {}}, "table_columns": "efc"}, "table_columns must be a list of df_final.csv column names"),
        ({"metrics": {"x": {}}, "table_columns": ["efc", 3]}, "table_columns must be a list"),
        ({"metrics": {"x": {}}, "table_columns": ["efc", "efc"]}, "table_columns: ['efc'] listed more than once"),
        ({"metrics": {"efc": {}}, "table_columns": ["efc"]}, "table_columns: ['efc'] already in metrics"),
    ])
    def test_message_names_the_file_and_the_problem(self, tmp_path, content, message):
        path = write_config(tmp_path, content)
        with pytest.raises(ConfigError) as err:
            load_config(path)
        assert message in str(err.value)
        assert str(path) in str(err.value)

    def test_rules_that_do_not_overlap_are_accepted(self):
        config = parse_config({"metrics": {"code": {"good": "== 1", "bad": "== 2"},
                                           "flip": {"good": "== 0", "bad": "!= 0"},
                                           "fd": {"good": "<= 15", "bad": "> 15"}}}).metrics
        assert config["code"].rules == {"good": ("==", 1.0), "bad": ("==", 2.0)}

    def test_byte_order_mark_is_accepted(self, tmp_path):
        path = tmp_path / "bom.json"
        path.write_text('﻿{"metrics": {"aqi": {}}}', encoding="utf-8")
        assert list(load_config(path).metrics) == ["aqi"]


class TestResolveMetrics:

    def test_follows_config_order_and_skips_absent_columns(self):
        config = parse_config({"metrics": {"b": {}, "a": {}, "zz": {}}}).metrics
        assert [m.column for m in resolve_metrics(config, ["a", "b", "c"])] == ["b", "a"]

    def test_label_defaults_to_the_column(self):
        assert parse_config({"metrics": {"aqi": {}}}).metrics["aqi"].label == "aqi"

    def test_entries_read_as_the_settings_tab_writes_them(self):
        metrics = parse_config({"metrics": {
            "a": {"label": " A "}, "b": {"label": ""},
            "c": {"good": "< 1", "otherwise": "other"}, "d": {"bad": "> 1", "otherwise": "good"},
            "e": {"good": "< 1", "otherwise": "bad"},
        }}).metrics
        assert [(m.label, m.otherwise) for m in metrics.values()] == [
            ("A", None), ("b", None), ("c", None), ("d", None), ("e", "bad")]

    def test_star_expands_in_table_order(self):
        config = parse_config({"metrics": {"frac_TRs_cens_*": {"label": "Fraction TRs Censored",
                                                               "bad": ">= 0.2"}}}).metrics
        metrics = resolve_metrics(config, ["ID", "frac_TRs_cens_2", "frac_TRs_cens_1"])
        assert [(m.column, m.label, m.entry_label) for m in metrics] == [
            ("frac_TRs_cens_2", "frac_TRs_cens_2", "Fraction TRs Censored"),
            ("frac_TRs_cens_1", "frac_TRs_cens_1", "Fraction TRs Censored"),
        ]
        assert all(m.rules == {"bad": (">=", 0.2)} for m in metrics)

    def test_matching_is_case_sensitive(self):
        config = parse_config({"metrics": {"TSNR": {}, "gcor*": {}}}).metrics
        assert resolve_metrics(config, ["tsnr", "GCOR"]) == []

    def test_a_column_is_used_once(self):
        config = parse_config({"metrics": {"cens_frac": {"label": "A"}, "cens_*": {}}}).metrics
        resolved = resolve_metrics(config, ["cens_frac", "cens_mot"])
        assert [(m.column, m.label) for m in resolved] == [("cens_frac", "A"), ("cens_mot", "cens_mot")]


class TestComparingConfigs:

    def test_metric_order_makes_a_different_config(self):
        first = parse_config({"metrics": {"a": {}, "b": {}}})
        second = parse_config({"metrics": {"b": {}, "a": {}}})
        assert first != second and not same_settings(first, second)

    def test_table_only_columns_in_another_order_set_the_same(self):
        first = parse_config({"metrics": {"a": {}}, "table_columns": ["x", "y"]})
        second = parse_config({"metrics": {"a": {}}, "table_columns": ["y", "x"]})
        assert first != second and same_settings(first, second)


class TestWritingConfigs:

    @pytest.mark.parametrize("pipeline", ["afni", "fmriprep"])
    def test_the_packaged_files_are_laid_out_as_the_writer_lays_them_out(self, pipeline):
        text = default_config_path(pipeline).read_text(encoding="utf-8")
        assert dump_config(json.loads(text)) == text
        assert dump_config(config_to_raw(load_config(default_config_path(pipeline)))) == text

    def test_a_written_config_reads_back_the_same(self):
        config = parse_config({"metrics": {
            "fd_mean": {"label": "Mean FD ≥ ok", "good": "< 0.123456789", "bad": "> 0.5000000001"},
            "frac_TRs_cens_*": {"bad": ">= 0.2", "step": 0.05},
            "efc": {},
            "size_t": {"good": "== 135", "otherwise": "bad"},
            "flagged": {"otherwise": "other"},
        }})
        assert parse_config(json.loads(dump_config(config_to_raw(config)))) == config

    def test_table_only_columns_read_back_the_same_on_one_line_after_the_metrics(self):
        config = parse_config({"metrics": {"fd_mean": {"bad": "> 0.5"}}, "table_columns": ["snr", "efc"]})
        text = dump_config(config_to_raw(config))
        assert text.endswith('  },\n  "table_columns": ["snr", "efc"]\n}\n')
        assert parse_config(json.loads(text)) == config

    def test_without_table_only_columns_the_field_is_left_out(self):
        assert "table_columns" not in dump_config({"metrics": {"a": {}}, "table_columns": []})
        assert parse_config({"metrics": {"a": {}}}).table_columns == ()

    def test_each_field_has_its_own_column(self):
        text = dump_config({"metrics": {"a": {"label": "A", "good": "< 1", "bad": "> 2"},
                                        "long_name": {"label": "B", "bad": "!= 0", "step": 1}}})
        assert text.splitlines()[2:4] == [
            '    "a":         {"label": "A", "good": "< 1", "bad": "> 2"},',
            '    "long_name": {"label": "B", ' + ' ' * len('"good": "< 1", ') + '"bad": "!= 0", "step": 1}',
        ]


class TestSavingConfigs:

    def test_a_new_file_is_written_without_a_backup(self, tmp_path):
        path = tmp_path / "mine.json"
        raw = {"metrics": {"fd_mean": {"label": "FD", "bad": "> 0.5"}}}
        config = save_config(path, raw)
        assert load_config(path) == config
        assert sorted(p.name for p in tmp_path.iterdir()) == ["mine.json"]

    def test_the_replaced_file_is_kept_as_bak(self, tmp_path):
        path = write_config(tmp_path, '{"metrics": {"fd_mean": {}}}')
        save_config(path, {"metrics": {"fd_mean": {"bad": "> 0.5"}}})
        assert (tmp_path / "my_config.json.bak").read_text(encoding="utf-8") == '{"metrics": {"fd_mean": {}}}'
        assert load_config(path).metrics["fd_mean"].rules == {"bad": (">", 0.5)}

    def test_an_invalid_config_is_not_written(self, tmp_path):
        path = write_config(tmp_path, '{"metrics": {"fd_mean": {}}}')
        with pytest.raises(ConfigError, match="metrics.fd_mean.bad"):
            save_config(path, {"metrics": {"fd_mean": {"bad": "0.5"}}})
        assert path.read_text(encoding="utf-8") == '{"metrics": {"fd_mean": {}}}'
        assert sorted(p.name for p in tmp_path.iterdir()) == ["my_config.json"]
