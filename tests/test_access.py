"""Tests for the session token gate and participant label checks on the local servers."""

import json
from pathlib import Path

import pytest
from flask import Flask

from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard
from fMRI_QCtoolkit.dashboard.fmriprep_rating_app import FMRIPrepRatingApp
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline
from fMRI_QCtoolkit.utils.access import AccessGate, is_loopback, url_host

from .test_fmriprep_rating import HTML_WITH_SESSION

TOKEN = "test-token"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "example_data" / "fmriprep"


@pytest.fixture
def gated():
    server = Flask(__name__)
    gate = AccessGate(server, TOKEN)

    @server.route("/page")
    def page():
        return "ok"

    return server, gate


@pytest.fixture
def rating_app(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sub-0030.html").write_text(HTML_WITH_SESSION, encoding="utf-8")
    return FMRIPrepRatingApp(data_dir, tmp_path / "output", token=TOKEN)


def logged_in(app):
    client = app.app.test_client()
    client.get(f"/sub-0030?token={TOKEN}")
    return client


class TestIsLoopback:

    @pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "127.0.0.2", "::1", "[::1]"])
    def test_loopback(self, host):
        assert is_loopback(host)

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "evil.example.com", ""])
    def test_not_loopback(self, host):
        assert not is_loopback(host)


class TestAccessGate:

    def test_no_token_is_denied(self, gated):
        server, _ = gated
        resp = server.test_client().get("/page")
        assert resp.status_code == 403
        assert "link printed in the terminal" in resp.get_data(as_text=True)

    def test_wrong_token_is_denied(self, gated):
        server, _ = gated
        assert server.test_client().get("/page?token=nope").status_code == 403

    def test_non_ascii_token_is_denied_not_crashed(self, gated):
        server, _ = gated
        assert server.test_client().get("/page?token=%C3%A9").status_code == 403

    def test_token_sets_cookie_and_strips_itself(self, gated):
        server, _ = gated
        client = server.test_client()

        resp = client.get(f"/page?token={TOKEN}&tab=2")

        assert resp.status_code == 302
        assert resp.headers["Location"] == "/page?tab=2"
        cookie = resp.headers["Set-Cookie"]
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
        assert client.get("/page").get_data(as_text=True) == "ok"

    def test_cookie_is_scoped_to_the_port_the_browser_sees(self, gated):
        server, _ = gated
        client = server.test_client()

        client.get(f"/page?token={TOKEN}", base_url="http://localhost:8888")

        assert client.get("/page", base_url="http://localhost:8888").status_code == 200
        assert client.get("/page", base_url="http://localhost:5003").status_code == 403

    def test_cookie_from_another_server_is_rejected(self, gated):
        server, _ = gated
        client = server.test_client()
        client.set_cookie("qc_token_default", "someone-elses-token", domain="localhost")
        assert client.get("/page").status_code == 403

    @pytest.mark.parametrize("host", ["evil.example.com", "evil.example.com:5003", "192.168.1.10:5003"])
    def test_foreign_host_header_is_denied_on_loopback_bind(self, gated, host):
        server, _ = gated
        resp = server.test_client().get(f"/page?token={TOKEN}", headers={"Host": host})
        assert resp.status_code == 403

    @pytest.mark.parametrize("host", ["localhost:5003", "127.0.0.1:5003", "[::1]:5003"])
    def test_loopback_host_header_is_accepted(self, gated, host):
        server, _ = gated
        resp = server.test_client().get(f"/page?token={TOKEN}", headers={"Host": host})
        assert resp.status_code == 302

    def test_non_loopback_bind_relies_on_token_only(self, gated):
        server, gate = gated
        gate.bind_host = "0.0.0.0"
        client = server.test_client()
        headers = {"Host": "node123.hpc.example.edu:5003"}

        assert client.get("/page", headers=headers).status_code == 403
        assert client.get(f"/page?token={TOKEN}", headers=headers).status_code == 302

    def test_link_carries_the_token(self, gated):
        _, gate = gated
        assert gate.link("http://localhost:5003", "/0030") == f"http://localhost:5003/0030?token={TOKEN}"

    def test_default_tokens_are_random(self):
        assert AccessGate(Flask("a")).token != AccessGate(Flask("b")).token


class TestRatingAppIsGated:

    def test_page_figures_and_save_need_the_token(self, rating_app):
        client = rating_app.app.test_client()
        assert client.get("/sub-0030").status_code == 403
        assert client.get("/sub-0030/figures/x.svg").status_code == 403
        assert client.post("/save_ratings", json={"id": "0030", "ratings": {}}).status_code == 403
        assert not (rating_app.output_dir / "sub-0030.json").exists()

    def test_save_works_after_login(self, rating_app):
        client = logged_in(rating_app)
        resp = client.post("/save_ratings", json={"id": "0030", "ratings": {"T1mask_run-1": "good"}, "notes": {}})
        assert resp.status_code == 200
        saved = json.loads((rating_app.output_dir / "sub-0030.json").read_text(encoding="utf-8"))
        assert saved["ratings"] == {"T1mask_run-1": "good"}


class TestParticipantLabelIsChecked:

    @pytest.mark.parametrize("pid", ["..%5C..%5C..%5Coutside", "sub-..%5C..%5C..%5Coutside", "0030%2E", "00%2030"])
    def test_page_rejects_non_bids_labels(self, rating_app, pid):
        (rating_app.data_dir.parent / "outside.html").write_text("SECRET", encoding="utf-8")
        resp = logged_in(rating_app).get(f"/{pid}")
        assert resp.status_code == 404
        assert "SECRET" not in resp.get_data(as_text=True)

    def test_figures_reject_non_bids_labels(self, rating_app):
        resp = logged_in(rating_app).get("/..%5C..%5Cdata/figures/x.svg")
        assert resp.status_code == 404

    @pytest.mark.parametrize("pid", ["../../escaped", "..\\..\\..\\escaped", "", 30, None])
    def test_save_rejects_non_bids_labels(self, rating_app, pid):
        resp = logged_in(rating_app).post("/save_ratings", json={"id": pid, "ratings": {}, "notes": {}})
        assert resp.status_code == 400
        assert not list(rating_app.data_dir.parent.rglob("*escaped*"))

    @pytest.mark.parametrize("body", [{"id": "0030", "ratings": [], "notes": {}}, {"id": "0030", "ratings": {}, "notes": "x"}])
    def test_save_rejects_malformed_payloads(self, rating_app, body):
        assert logged_in(rating_app).post("/save_ratings", json=body).status_code == 400

    def test_save_rejects_non_json(self, rating_app):
        resp = logged_in(rating_app).post("/save_ratings", data="id=0030", content_type="text/plain")
        assert resp.status_code == 400

    def test_template_escapes_the_label_as_js(self, rating_app):
        page = logged_in(rating_app).get("/sub-0030").get_data(as_text=True)
        assert 'window.participantId = "0030";' in page


class TestDashboardIsGated:

    @pytest.fixture
    def dashboard(self):
        pipeline = FMRIPrepPipeline.from_saved_data(
            data_file=EXAMPLES / "df_final.csv",
            lollipop_file=EXAMPLES / "lollipop_chart_data.csv",
            task="rest",
        )
        return FMRIPrepDashboard(pipeline, task="rest", token=TOKEN)

    def test_layout_needs_the_token(self, dashboard):
        client = dashboard.app.server.test_client()
        assert client.get("/").status_code == 403
        assert client.get("/_dash-layout").status_code == 403

        assert client.get(f"/?token={TOKEN}").status_code == 302
        assert client.get("/_dash-layout").status_code == 200


class TestPrintedLinkHost:

    @pytest.mark.parametrize("bind", ["127.0.0.1", "localhost", "node123.hpc.edu"])
    def test_named_hosts_pass_through(self, bind):
        assert url_host(bind) == bind

    @pytest.mark.parametrize("bind", ["::1", "[::1]"])
    def test_ipv6_gets_brackets(self, bind):
        assert url_host(bind) == "[::1]"

    @pytest.mark.parametrize("bind", ["0.0.0.0", "::"])
    def test_wildcard_uses_the_machine_name(self, bind):
        import socket
        assert url_host(bind) == socket.gethostname()
