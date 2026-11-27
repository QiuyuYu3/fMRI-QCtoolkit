"""
Shared helpers for the dashboard tests: build a dashboard on a table, read its layout, and drive its callbacks.
"""

import json

import numpy as np
import pandas as pd
from dash._utils import stringify_id

from fMRI_QCtoolkit.dashboard.afni_app import AFNIDashboard
from fMRI_QCtoolkit.dashboard.custom_app import CustomDashboard
from fMRI_QCtoolkit.data.afni_pipeline import AFNIPipeline
from fMRI_QCtoolkit.data.custom_pipeline import CustomPipeline
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline
from fMRI_QCtoolkit.utils.filter_components_utils import RANGE, STATUS


def make_dashboard(cls, df, tmp_path, config=None):
    data_file = tmp_path / "df_final.csv"
    df.to_csv(data_file, index=False)
    pipeline_cls = {AFNIDashboard: AFNIPipeline, CustomDashboard: CustomPipeline}.get(cls, FMRIPrepPipeline)
    return cls(pipeline_cls.from_saved_data(data_file, task="test"), task="test", config_path=config)


def layout_components(dashboard):
    return [c for c in dashboard.build_layout()._traverse() if getattr(c, "id", None) is not None]


def layout_values(dashboard):
    """Filter values as the page sends them when it first opens."""
    comps = layout_components(dashboard)

    def by_column(kind):
        return {c.id["column"]: c.value for c in comps if isinstance(c.id, dict) and c.id["type"] == kind}

    named = {c.id: c for c in comps if isinstance(c.id, str)}
    ratings = [named[f"{g}_dropdown"].value for g in dashboard.rating_columns()]
    return by_column(RANGE), by_column(STATUS), ratings


def shown_ids(dashboard, ranges, statuses, ratings):
    positions = dashboard.filtered_positions(ranges, statuses, ratings)
    return dashboard.processor.get_data().iloc[positions]["ID"].tolist()


def dash_call(dashboard, output, values, changed, comps=None):
    """POST the callback that has `output` as the browser would; inputs not in `values` keep their layout values.

    `values` and `changed` name a component by its id as stringify_id writes it; a pattern id ({"key": ALL})
    covers every matching component of `comps`, by default the layout's.
    """
    # A second writer of an output carries an @ suffix there, so the plain name finds the first writer
    key, spec = next((k, s) for k, s in dashboard.app.callback_map.items() if output in k.strip(".").split("..."))
    comps = {stringify_id(c.id): c for c in (comps if comps is not None else layout_components(dashboard))}

    def instances(ident):
        if not ident.startswith("{"):
            return None
        pattern = json.loads(ident)
        return [c.id for c in comps.values() if isinstance(c.id, dict) and set(c.id) == set(pattern)
                and all(v == ["ALL"] or c.id[k] == v for k, v in pattern.items())]

    def value(ident, prop):
        name = stringify_id(ident)
        return values[(name, prop)] if (name, prop) in values else getattr(comps.get(name), prop, None)

    def with_values(item):
        found = instances(item["id"])
        if found is None:
            return dict(item, value=value(item["id"], item["property"]))
        return [{"id": i, "property": item["property"], "value": value(i, item["property"])} for i in found]

    def output_spec(text):
        ident, prop = text.rsplit(".", 1)
        found = instances(ident)
        return {"id": ident, "property": prop} if found is None else [{"id": i, "property": prop} for i in found]

    outputs = [output_spec(o) for o in key.strip(".").split("...")]
    client = dashboard.app.server.test_client()
    client.get(f"/?token={dashboard.gate.token}")
    return client.post("/_dash-update-component", json={
        "output": key,
        "outputs": outputs if key.startswith("..") else outputs[0],
        "inputs": [with_values(item) for item in spec["inputs"]],
        "state": [with_values(item) for item in spec.get("state", [])],
        "changedPropIds": [changed],
    })


FD_MEAN_RANGE = stringify_id({"type": RANGE, "column": "fd_mean"}) + ".value"


def afni_runs():
    good = {"cens_frac": 0.1, "cens_mot": 0.05, "cens_displace": 3.0, "TSNR": 200.0,
            "DF_frac": 0.9, "flip_guess": 0, "GCOR": 0.1, "frac_TRs_cens_1": 0.0}
    changes = {
        "001": {},
        "002": {"cens_frac": 0.2},
        "003": {"cens_frac": 0.1999},
        "004": {"flip_guess": 1},
        "005": {"TSNR": 100.0},
        "006": {"frac_TRs_cens_1": 0.2},
        "007": {"DF_frac": 0.6},
        "008": {"GCOR": np.nan},
    }
    return pd.DataFrame([{"ID": run_id, **good, **change} for run_id, change in changes.items()])
