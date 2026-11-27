import numpy as np
import pandas as pd
import pytest

from fMRI_QCtoolkit.dashboard.config import Metric
from fMRI_QCtoolkit.utils.filter_components_utils import (
    RANGE,
    STATUS,
    create_metric_filter,
    create_qualitative_dropdown,
    create_rules_summary,
    default_statuses,
    mark_key,
    rating_options,
    slider_bounds,
    status_options,
)

CENS_FRAC = Metric("cens_frac", "Censor Fraction", {"good": ("<", 0.15), "bad": (">=", 0.2)},
                   entry="cens_frac", entry_label="Censor Fraction")
TSNR = Metric("TSNR", "TSNR Average", {"good": (">", 150.0)}, entry="TSNR", entry_label="TSNR Average")
FLIP = Metric("flip_guess", "Flip Guess", {"bad": ("!=", 0.0)}, step=1,
              entry="flip_guess", entry_label="Flip Guess")
DVARS = Metric("dvars_nstd", "DVARS", {}, entry="dvars_nstd", entry_label="DVARS")


def by_id(component, component_id):
    return next(c for c in component._traverse() if getattr(c, "id", None) == component_id)


class TestSliderBounds:

    def test_covers_the_data_and_the_threshold_lines(self):
        assert slider_bounds([0.02, 0.1], CENS_FRAC) == (0.02, 0.2, 0.001)

    def test_step_from_the_config_wins(self):
        assert slider_bounds([0, 1, 0], FLIP) == (0.0, 1.0, 1)

    def test_equality_rules_add_no_line(self):
        assert slider_bounds([0, 1], Metric("x", "X", {"good": ("==", 5.0)}))[:2] == (0.0, 1.0)

    def test_missing_data_without_thresholds(self):
        assert slider_bounds([np.nan, None], DVARS) == (0.0, 1.0, 0.01)

    def test_constant_column_gets_a_width(self):
        lo, hi, _ = slider_bounds([3.0, 3.0], DVARS)
        assert lo == 3.0 and hi > lo

    @pytest.mark.parametrize("values", [[0.10370001, 0.4499], [101.3, 299.7], [0.0123, 0.0125]])
    def test_every_value_lies_inside(self, values):
        lo, hi, _ = slider_bounds(values, DVARS)
        assert lo <= min(values) and hi >= max(values)

    def test_infinite_values_are_left_out(self):
        assert slider_bounds([0.1, 0.5, np.inf, -np.inf], DVARS) == slider_bounds([0.1, 0.5], DVARS)
        assert slider_bounds([np.inf], DVARS) == (0.0, 1.0, 0.01)


class TestStatusChecklist:

    @pytest.mark.parametrize("metric,options,defaults", [
        (CENS_FRAC, ["good", "other", "bad", "NA"], ["good", "other", "NA"]),
        (TSNR, ["good", "other", "NA"], ["good", "other", "NA"]),
        (FLIP, ["good", "bad", "NA"], ["good", "NA"]),
        (DVARS, ["NA"], ["NA"]),
        (Metric("x", "X", {}, otherwise="other"), ["other", "NA"], ["other", "NA"]),
        (Metric("x", "X", {"good": ("==", 1.0)}, otherwise="bad"), ["good", "bad", "NA"], ["good", "NA"]),
    ])
    def test_bad_is_unticked_by_default(self, metric, options, defaults):
        assert [o["value"] for o in status_options(metric)] == options
        assert default_statuses(metric) == defaults

    def test_without_thresholds_the_box_only_toggles_missing_values(self):
        assert status_options(DVARS) == [{"label": "Include NA", "value": "NA"}]


class TestMetricFilter:

    def test_slider_starts_at_full_range_with_threshold_marks(self):
        component = create_metric_filter(CENS_FRAC, (0.0, 0.3, 0.01))
        slider = by_id(component, {"type": RANGE, "column": "cens_frac"})
        assert (slider.min, slider.max, slider.value) == (0.0, 0.3, [0.0, 0.3])
        assert slider.marks["0.15"]["label"] == "0.15"
        assert slider.marks["0.2"]["label"] == "0.2"
        assert by_id(component, {"type": STATUS, "column": "cens_frac"}).value == ["good", "other", "NA"]

    @pytest.mark.parametrize("metric, bounds, room", [
        (CENS_FRAC, (0.0, 0.3, 0.01), "26px"),
        (TSNR, (150.0, 300.0, 1), "26px"),
        (FLIP, (0.0, 1.0, 1), "0"),
        (DVARS, (0.0, 1.0, 0.01), "0"),
    ])
    def test_the_label_leaves_room_for_threshold_labels(self, metric, bounds, room):
        label = next(c for c in create_metric_filter(metric, bounds)._traverse() if type(c).__name__ == "Label")
        assert label.style["margin-bottom"] == room


class TestRulesSummary:

    @staticmethod
    def text(component):
        nodes = [component, *component._traverse()]
        return [c.children for c in nodes if type(c).__name__ in ("P", "Li")]

    def test_one_line_per_config_entry(self):
        frac_1 = Metric("frac_TRs_cens_1", "frac_TRs_cens_1", {"bad": (">=", 0.2)},
                        entry="frac_TRs_cens_*", entry_label="Fraction TRs Censored")
        frac_2 = Metric("frac_TRs_cens_2", "frac_TRs_cens_2", {"bad": (">=", 0.2)},
                        entry="frac_TRs_cens_*", entry_label="Fraction TRs Censored")
        lines = self.text(create_rules_summary([CENS_FRAC, TSNR, FLIP, DVARS, frac_1, frac_2]))
        assert lines[1:] == [
            "Censor Fraction: good < 0.15, bad ≥ 0.2",
            "TSNR Average: good > 150",
            "Flip Guess: bad ≠ 0",
            "Fraction TRs Censored: bad ≥ 0.2",
        ]

    def test_no_thresholds(self):
        assert "no run is hidden" in self.text(create_rules_summary([DVARS]))[0]


class TestQualitativeDropdown:

    def test_offers_the_ratings_in_the_column_all_selected(self):
        values = pd.Series(["bad", None, "good", "good"])
        dropdown = by_id(create_qualitative_dropdown("FINAL_rating", "Final", values), "FINAL_rating_dropdown")
        assert [o["label"] for o in dropdown.options] == ["Good", "Bad", "NA"]
        assert dropdown.value == ["good", "bad", "NA"]

    @pytest.mark.parametrize("values,offered", [
        (["other", "good", "bad"], ["good", "other", "bad"]),
        (["bad", "good"], ["good", "bad"]),
        ([None, None], ["NA"]),
    ])
    def test_na_is_offered_only_for_empty_cells(self, values, offered):
        assert [o["value"] for o in rating_options(pd.Series(values, dtype=object))] == offered


class TestMarkKeys:
    """Dash 2 keeps a slider mark only if its key reads as JavaScript prints the number."""

    @pytest.mark.parametrize("value, key", [
        (15.0, "15"), (35.0, "35"), (0.443, "0.443"), (5.3, "5.3"), (0.0, "0"), (-0.35, "-0.35"),
        (0.00005, "0.00005"), (1e16, "10000000000000000"), (1e-7, "1e-7"), (1.5e-7, "1.5e-7"), (1e21, "1e+21"),
    ])
    def test_keys_match_javascript(self, value, key):
        assert mark_key(value) == key

    def test_whole_number_thresholds_get_their_labels(self):
        metric = Metric("fd_perc", "FD", {"good": ("<=", 15.0), "bad": (">", 20.0)}, entry="fd_perc", entry_label="FD")
        slider = by_id(create_metric_filter(metric, (5.3, 35.0, 0.1)), {"type": RANGE, "column": "fd_perc"})
        assert sorted(slider.marks) == ["15", "20", "35", "5.3"]

    def test_threshold_labels_sit_above_the_track_and_the_ends_below(self):
        metric = Metric("fd_perc", "FD", {"good": ("<=", 15.0), "bad": (">", 20.0)}, entry="fd_perc", entry_label="FD")
        marks = by_id(create_metric_filter(metric, (5.3, 35.0, 0.1)), {"type": RANGE, "column": "fd_perc"}).marks
        assert {key: marks[key]["style"]["color"] for key in ("15", "20")} == {"15": "#3B7D23", "20": "#C0392B"}
        assert all(marks[key]["style"]["bottom"] == "auto" for key in ("15", "20"))
        assert (marks["5.3"], marks["35"]) == ("5.3", "35")

    @pytest.mark.parametrize("rules, expected", [
        ({"good": (">", 150.0), "bad": ("<", 100.0)}, {"100": "translateX(-100%)", "150": "translateX(0%)"}),
        ({"good": ("<", 0.2), "bad": (">=", 0.3)}, {"0.2": "translateX(-100%)", "0.3": "translateX(0%)"}),
    ])
    def test_two_threshold_labels_point_away_from_each_other(self, rules, expected):
        metric = Metric("m", "M", rules, entry="m", entry_label="M")
        marks = by_id(create_metric_filter(metric, (0.0, 300.0, 0.1)), {"type": RANGE, "column": "m"}).marks
        assert {key: marks[key]["style"]["transform"] for key in expected} == expected

    @pytest.mark.parametrize("rules", [
        {"good": (">", 150.0)},
        {"good": ("<", 0.2), "bad": (">=", 0.2)},
    ])
    def test_a_single_threshold_label_stays_centred(self, rules):
        metric = Metric("m", "M", rules, entry="m", entry_label="M")
        marks = by_id(create_metric_filter(metric, (0.0, 300.0, 0.1)), {"type": RANGE, "column": "m"}).marks
        assert [mark for mark in marks.values() if isinstance(mark, dict) and "transform" in mark["style"]] == []
