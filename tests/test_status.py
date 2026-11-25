import numpy as np
import pandas as pd
import pytest

from fMRI_QCtoolkit.dashboard.config import default_config_path, load_config
from fMRI_QCtoolkit.utils.status import (
    assign_status,
    describe_other,
    format_rule,
    get_status_colors,
    get_status_mapping,
    negate_rule,
    overlap,
    parse_rule,
    rated_tiers,
)

# What the 1.x if-elif rules in utils/status.py returned at these values
LEGACY_AFNI = {
    'DF_frac': [(0.5, 'bad'), (0.6, 'bad'), (0.6001, 'other'), (0.65, 'other'), (0.7, 'other'), (0.7001, 'good'), (0.8, 'good')],
    'cens_frac': [(0.1, 'good'), (0.1499, 'good'), (0.15, 'other'), (0.17, 'other'), (0.1999, 'other'), (0.2, 'bad'), (0.3, 'bad')],
    'cens_mot': [(0.05, 'good'), (0.0999, 'good'), (0.1, 'other'), (0.12, 'other'), (0.1499, 'other'), (0.15, 'bad'), (0.2, 'bad')],
    'cens_displace': [(5, 'good'), (5.99, 'good'), (6, 'other'), (7, 'other'), (7.99, 'other'), (8, 'bad'), (9, 'bad')],
    'GCOR': [(0.1, 'good'), (0.1499, 'good'), (0.15, 'other'), (0.17, 'other'), (0.1999, 'other'), (0.2, 'bad'), (0.25, 'bad')],
    'flip_guess': [(0, 'good'), (1, 'bad')],
    'TSNR': [(100, 'other'), (150, 'other'), (150.01, 'good'), (200, 'good')],
}
LEGACY_FMRIPREP = {
    'fd_perc': [(10, 'good'), (15, 'good'), (15.01, 'other'), (18, 'other'), (20, 'other'), (20.01, 'bad'), (30, 'bad')],
    'fd_mean': [(0.1, 'good'), (0.1999, 'good'), (0.2, 'other'), (0.25, 'other'), (0.2999, 'other'), (0.3, 'bad'), (0.4, 'bad')],
}


def packaged_rules(pipeline, key):
    return load_config(default_config_path(pipeline)).metrics[key].rules


class TestPackagedThresholdsMatchTheOldRules:

    @pytest.mark.parametrize("column,cases", LEGACY_AFNI.items(), ids=LEGACY_AFNI)
    def test_afni(self, column, cases):
        values, expected = zip(*cases)
        assert assign_status(list(values), packaged_rules("afni", column)).tolist() == list(expected)

    @pytest.mark.parametrize("column,cases", LEGACY_FMRIPREP.items(), ids=LEGACY_FMRIPREP)
    def test_fmriprep(self, column, cases):
        values, expected = zip(*cases)
        assert assign_status(list(values), packaged_rules("fmriprep", column)).tolist() == list(expected)

    @pytest.mark.parametrize("column", ["tsnr", "gcor"])
    def test_fmriprep_tsnr_and_gcor_have_no_thresholds(self, column):
        assert packaged_rules("fmriprep", column) == {}

    def test_censoring_per_stimulus_is_bad_from_point_two(self):
        rules = packaged_rules("afni", "frac_TRs_cens_*")
        assert assign_status([0.1999, 0.2], rules).tolist() == ["good", "bad"]


class TestAssignStatus:

    def test_missing_values_are_na(self):
        status = assign_status([np.nan, None, pd.NA, "n/a", 0.1], {"bad": (">=", 0.2)})
        assert status.tolist() == ["NA", "NA", "NA", "NA", "good"]

    def test_no_rules_means_good(self):
        assert assign_status([0.0, 1e6], {}).tolist() == ["good", "good"]

    def test_other_is_between_good_and_bad(self):
        rules = {"good": ("<", 0.1), "bad": (">=", 0.2)}
        assert assign_status([0.05, 0.1, 0.15, 0.2, 0.3], rules).tolist() == ["good", "other", "other", "bad", "bad"]

    def test_with_only_a_bad_rule_the_rest_is_good(self):
        assert assign_status([0, 1, 2], {"bad": ("!=", 0.0)}).tolist() == ["good", "bad", "bad"]

    def test_with_only_a_good_rule_the_rest_is_other(self):
        assert assign_status([100, 150, 151], {"good": (">", 150.0)}).tolist() == ["other", "other", "good"]

    @pytest.mark.parametrize("rules,tiers", [
        ({}, []),
        ({"bad": (">=", 0.2)}, ["good", "bad"]),
        ({"good": (">", 150.0)}, ["good", "other"]),
        ({"good": ("<", 0.15), "bad": (">=", 0.2)}, ["good", "other", "bad"]),
        ({"good": ("<=", 15.0), "bad": (">", 15.0)}, ["good", "bad"]),
        ({"good": ("==", 0.0), "bad": ("!=", 0.0)}, ["good", "bad"]),
    ])
    def test_rated_tiers_are_the_statuses_the_rules_can_give(self, rules, tiers):
        assert rated_tiers(rules) == tiers

    @pytest.mark.parametrize("rules,other", [
        ({"good": ("<=", 15.0), "bad": (">", 25.0)}, "15 < x ≤ 25"),
        ({"good": ("<", 0.15), "bad": (">=", 0.2)}, "0.15 ≤ x < 0.2"),
        ({"good": (">", 0.7), "bad": ("<=", 0.6)}, "0.6 < x ≤ 0.7"),
        ({"good": (">", 150.0)}, "x ≤ 150"),
        ({"good": ("==", 1.0), "bad": ("==", 2.0)}, "x ≠ 1 and x ≠ 2"),
        ({"bad": (">=", 0.2)}, None),
        ({"good": ("<=", 20.0), "bad": (">", 20.0)}, None),
    ])
    def test_describe_other_gives_the_values_between_good_and_bad(self, rules, other):
        assert describe_other(rules) == other

    @pytest.mark.parametrize("good,bad,both", [
        (("<", 0.25), (">=", 0.2), 0.2),
        (("<=", 0.2), (">=", 0.2), 0.2),
        (("<", 0.2), (">=", 0.2), None),
        ((">", 0.7), ("<=", 0.6), None),
        (("==", 0.0), ("!=", 0.0), None),
    ])
    def test_overlap_finds_a_value_both_rules_take(self, good, bad, both):
        assert overlap(good, bad) == both

    @pytest.mark.parametrize("op,negated", [(">", "<="), (">=", "<"), ("<", ">="), ("<=", ">"), ("==", "!="), ("!=", "==")])
    def test_negated_rules_split_every_value(self, op, negated):
        values = [0.9, 1.0, 1.1]
        assert negate_rule((op, 1.0)) == (negated, 1.0)
        assert assign_status(values, {"bad": (op, 1.0)}).tolist() == assign_status(values, {"good": (negated, 1.0)}).replace({"other": "bad"}).tolist()

    def test_keeps_the_index(self):
        values = pd.Series([0.1, 0.3], index=[5, 7])
        assert assign_status(values, {"bad": (">", 0.2)}).to_dict() == {5: "good", 7: "bad"}

    def test_nullable_dtype(self):
        values = pd.Series([0.1, None, 0.3], dtype="Float64")
        assert assign_status(values, {"bad": (">", 0.2)}).tolist() == ["good", "NA", "bad"]


class TestParseRule:

    @pytest.mark.parametrize("text,expected", [
        (">= 0.2", (">=", 0.2)),
        ("<=150", ("<=", 150.0)),
        ("  !=  0 ", ("!=", 0.0)),
        ("> -1.5e-3", (">", -0.0015)),
        ("== .5", ("==", 0.5)),
        ("< 20.", ("<", 20.0)),
    ])
    def test_valid(self, text, expected):
        assert parse_rule(text) == expected

    @pytest.mark.parametrize("text", ["=> 0.2", ">=", "0.2", ">= abc", "≥ 0.2", ">= 0.2 0.3", 0.2, None])
    def test_invalid(self, text):
        with pytest.raises(ValueError, match="is not a rule"):
            parse_rule(text)

    def test_format(self):
        assert format_rule((">=", 0.2)) == ">= 0.2"
        assert format_rule((">", 15.0)) == "> 15"
        assert format_rule(("<=", 150.0), symbols=True) == "≤ 150"

    @pytest.mark.parametrize("value", [0.1 + 0.2, 1234567.891, 1e-7, 2.5e16, -0.35])
    def test_rules_keep_every_digit(self, value):
        assert parse_rule(format_rule((">", value))) == (">", value)


class TestStatusHelpers:
    """Test helper functions for status mappings and colors"""

    def test_status_mapping(self):
        """Test status mapping returns correct indices"""
        mapping = get_status_mapping()
        assert mapping['NA'] == 0
        assert mapping['bad'] == 1
        assert mapping['other'] == 2
        assert mapping['good'] == 3

    def test_status_colors(self):
        """Test status colors are properly defined"""
        colors = get_status_colors()
        assert 0 in colors  # NA
        assert 1 in colors  # bad
        assert 2 in colors  # other
        assert 3 in colors  # good
        assert all(c.startswith('#') for c in colors.values())

    def test_colors_match_mapping(self):
        """Ensure color keys align with mapping values"""
        mapping = get_status_mapping()
        colors = get_status_colors()

        for label, idx in mapping.items():
            assert idx in colors, f"Missing color for {label} (index {idx})"
