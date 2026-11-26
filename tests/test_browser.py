"""
Browser tests for values the page itself holds and sends late; they skip without Playwright and its Chromium.
"""

import io
import json
import os
import re
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from dash._utils import stringify_id
from werkzeug.serving import make_server

from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline


def skip_or_fail(reason):
    # CI jobs that install the browser set this, so a broken install fails instead of skipping
    if os.environ.get("FMRIQC_REQUIRE_BROWSER"):
        pytest.fail(reason)
    pytest.skip(reason, allow_module_level=True)


try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:
    skip_or_fail("Playwright is not installed")

KEY = "n => n.data.ID + '-' + n.data.run"
OTHER = ["002-1", "002-2", "009-2"]


def runs():
    # 12 subjects with 2 runs; 011 and 012 are bad on fd_mean, so the default view shows 20 runs on two pages
    rows = []
    for i in range(1, 13):
        sid = f"{i:03d}"
        for run in (1, 2):
            rows.append({"ID": sid, "session": "01", "run": run, "task": "rest",
                         "fd_perc": 17.0 if f"{sid}-{run}" in OTHER else 5.0,
                         "fd_mean": 0.35 if sid in ("011", "012") else 0.1,
                         "efc": 0.5 + i / 100, "Final": "good"})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def browser():
    try:
        with sync_playwright() as p:
            try:
                launched = p.chromium.launch()
            except PlaywrightError as e:
                skip_or_fail(f"Playwright has no Chromium: {str(e).splitlines()[0]}")
            yield launched
            launched.close()
    except PlaywrightError as e:
        skip_or_fail(f"Playwright did not start: {str(e).splitlines()[0]}")


class Session:
    def __init__(self, page, config):
        self.page, self.config, self.errors = page, config, []
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.on("pageerror", lambda e: self.errors.append(str(e)))

    def by_id(self, ident):
        return self.page.locator(f"[id='{stringify_id(ident)}']" if isinstance(ident, dict) else f"#{ident}")

    def open_tab(self, label):
        self.page.get_by_text(label, exact=True).click()

    def tick(self, position):
        self.page.locator(f"#datatable .ag-pinned-left-cols-container .ag-row[row-id='{position}'] "
                          "input.ag-checkbox-input").click()

    def next_page(self):
        self.page.evaluate("() => dash_ag_grid.getApi('datatable').paginationGoToNextPage()")

    def status_box(self, column, level):
        # Dash 2 checklist inputs carry no value attribute, so find the box by its label
        label = self.by_id({"type": "metric-status", "column": column}).locator("label").filter(
            has_text=re.compile(f"^{re.escape(level)}$"))
        return label.locator("input")

    def grid_rows(self, grid):
        return sorted(self.page.evaluate(f"""() => {{ const out = [];
            dash_ag_grid.getApi('{grid}').forEachNode(n => out.push(({KEY})(n))); return out; }}"""))

    def grid_selection(self):
        return sorted(self.page.evaluate(f"() => dash_ag_grid.getApi('datatable').getSelectedNodes().map({KEY})"))

    def panel(self):
        if not self.by_id("selected-rows-table").count():
            return self.by_id("selected-rows-display").inner_text().strip()
        return self.grid_rows("selected-rows-table")

    def download(self):
        with self.page.expect_download() as dl:
            self.by_id("download-button").click()
        rows = pd.read_csv(io.StringIO(Path(dl.value.path()).read_text(encoding="utf-8")), dtype={"ID": str})
        return sorted(f"{i}-{r}" for i, r in zip(rows["ID"], rows["run"])) if "ID" in rows else []

    def eventually(self, read, expected, timeout=15):
        deadline = time.monotonic() + timeout
        while (got := read()) != expected and time.monotonic() < deadline:
            self.page.wait_for_timeout(200)
        return got

    def assert_selection(self, expected):
        want = sorted(expected)
        assert self.eventually(self.grid_selection, want) == want
        assert self.eventually(self.panel, want or "No row selected.") == (want or "No row selected.")
        assert self.download() == want

    def form_keys(self):
        return self.page.evaluate("""() => [...document.querySelectorAll('input[id]')].map(e => e.id)
            .filter(i => i.includes('"thr-label"')).map(i => JSON.parse(i).key)""")

    def saved(self):
        return json.loads(self.config.read_text(encoding="utf-8"))["metrics"] if self.config.exists() else {}


@pytest.fixture()
def session(browser, tmp_path):
    data_file = tmp_path / "df_final.csv"
    runs().to_csv(data_file, index=False)
    config = tmp_path / "my_config.json"
    board = FMRIPrepDashboard(FMRIPrepPipeline.from_saved_data(data_file, task="rest"), task="rest",
                              config_path=config)
    server = make_server("127.0.0.1", 0, board.app.server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(f"http://127.0.0.1:{server.server_port}/?token={board.gate.token}")
    page.wait_for_selector("#main-tabs")
    s = Session(page, config)
    s.open_tab("Table")
    page.wait_for_selector("#datatable .ag-row")
    assert s.eventually(lambda: len(s.grid_rows("datatable")), 20) == 20
    yield s
    context.close()
    server.shutdown()


def test_hiding_every_selected_row_empties_selected_rows_and_download(session):
    session.next_page()
    session.tick(17)
    session.assert_selection(["009-2"])
    session.status_box("fd_perc", "other").click()
    session.assert_selection([])
    session.status_box("fd_perc", "other").click()
    assert session.eventually(lambda: len(session.grid_rows("datatable")), 20) == 20
    session.assert_selection(session.grid_selection())
    assert not session.errors


def test_hiding_some_selected_rows_keeps_the_rest(session):
    session.tick(0)
    session.next_page()
    session.tick(17)
    session.assert_selection(["001-1", "009-2"])
    session.status_box("fd_perc", "other").click()
    session.assert_selection(["001-1"])
    assert not session.errors


def test_moving_a_row_right_after_typing_keeps_the_typed_value(session):
    session.open_tab("Settings")
    good = session.by_id({"type": "thr-good-value", "key": "fd_perc"})
    good.fill("18")
    session.by_id({"type": "thr-down", "key": "fd_perc"}).click()
    assert session.eventually(lambda: session.form_keys()[:2], ["fd_mean", "fd_perc"]) == ["fd_mean", "fd_perc"]
    assert session.by_id({"type": "thr-good-value", "key": "fd_perc"}).input_value() == "18"
    counts = session.by_id({"type": "thr-counts", "key": "fd_perc"})
    assert session.eventually(lambda: "other 0" in counts.inner_text(), True)
    assert not session.errors


@pytest.mark.parametrize("kind, metric, typed, field, stored", [
    ("good-value", "fd_perc", "18", "good", "<= 18"),
    ("label", "fd_mean", "Mean FD", "label", "Mean FD"),
])
def test_save_right_after_typing_saves_the_typed_value(session, kind, metric, typed, field, stored):
    session.open_tab("Settings")
    session.by_id({"type": f"thr-{kind}", "key": metric}).fill(typed)
    # A quick click lands while the form still looks untouched and Save is faded
    with session.page.expect_navigation():
        session.by_id("thr-save").click(force=True)
    assert session.eventually(lambda: session.saved().get(metric, {}).get(field), stored) == stored
    assert not session.errors


def test_a_value_typed_back_after_enter_is_the_one_saved(session):
    session.open_tab("Settings")
    good = session.by_id({"type": "thr-good-value", "key": "fd_perc"})
    counts = session.by_id({"type": "thr-counts", "key": "fd_perc"})
    good.fill("18")
    good.press("Enter")
    assert session.eventually(lambda: "other 0" in counts.inner_text(), True)
    good.fill("15")
    with session.page.expect_navigation():
        session.by_id("thr-save").click()
    assert session.eventually(lambda: session.saved().get("fd_perc", {}).get("good"), "<= 15") == "<= 15"
    assert not session.errors
