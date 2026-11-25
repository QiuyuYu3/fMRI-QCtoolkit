import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fMRI_QCtoolkit import cli
from fMRI_QCtoolkit.dashboard.afni_app import AFNIDashboard
from fMRI_QCtoolkit.dashboard.config import default_config_path
from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "example_data" / "fmriprep"
runner = CliRunner()


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "find_free_port", lambda **kwargs: 5123)
    for cls in (AFNIDashboard, FMRIPrepDashboard):
        monkeypatch.setattr(cls, "run", lambda self, **kwargs: calls.append((self, kwargs)))
    return calls


def test_dashboard_fmriprep_launches(launched):
    result = runner.invoke(cli.app, ["dashboard", "fmriprep", "--data-file", str(EXAMPLES / "df_final.csv"),
                                     "--task", "rest"])
    assert result.exit_code == 0, result.output
    assert [(type(d), kwargs) for d, kwargs in launched] == [
        (FMRIPrepDashboard, {"host": "127.0.0.1", "port": 5123, "debug": False})]
    assert launched[0][0].config_path == default_config_path("fmriprep")


def test_dashboard_afni_launches(launched, tmp_path, sample_afni_data):
    data_file = tmp_path / "df_final.csv"
    sample_afni_data.to_csv(data_file, index=False)

    result = runner.invoke(cli.app, ["dashboard", "afni", "--data-file", str(data_file), "--task", "rest"])
    assert result.exit_code == 0, result.output
    assert [type(d) for d, _ in launched] == [AFNIDashboard]


@pytest.mark.parametrize("pipeline", ["afni", "fmriprep"])
def test_lollipop_file_option_is_gone(launched, pipeline):
    result = runner.invoke(cli.app, ["dashboard", pipeline, "--data-file", str(EXAMPLES / "df_final.csv"),
                                     "--lollipop-file", "lollipop_chart_data.csv", "--task", "rest"])
    assert result.exit_code == 2
    assert "No such option" in result.output
    assert launched == []


def test_directory_given_as_data_file_is_refused(launched, tmp_path):
    result = runner.invoke(cli.app, ["dashboard", "fmriprep", "--data-file", str(tmp_path), "--task", "rest"])
    assert result.exit_code == 1
    assert "not a file" in result.output
    assert launched == []


def test_file_given_as_input_dir_is_refused(tmp_path):
    a_file = tmp_path / "x.txt"
    a_file.write_text("")
    result = runner.invoke(cli.app, ["prep", "afni", "--input-dir", str(a_file), "--output-dir", str(tmp_path / "out"),
                                     "--task", "rest", "--prefix", "sub-"])
    assert result.exit_code == 1
    assert "not a directory" in result.output


class TestDashboardConfigOption:

    def run_fmriprep(self, config):
        return runner.invoke(cli.app, ["dashboard", "fmriprep", "--data-file", str(EXAMPLES / "df_final.csv"),
                                       "--task", "rest", "--config", str(config)])

    def test_thresholds_come_from_the_given_file(self, launched, tmp_path):
        config = tmp_path / "lab.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {"other": ">= 0.25", "bad": ">= 0.5"}}}))

        result = self.run_fmriprep(config)

        assert result.exit_code == 0, result.output
        dashboard = launched[0][0]
        assert dashboard.config_path == config
        assert [(m.column, m.rules) for m in dashboard.metrics] == [
            ("fd_mean", {"other": (">=", 0.25), "bad": (">=", 0.5)})]

    def test_a_broken_config_stops_before_launch(self, launched, tmp_path):
        config = tmp_path / "lab.json"
        config.write_text(json.dumps({"metrics": {"fd_mean": {"bad": "=> 0.5"}}}))

        result = self.run_fmriprep(config)

        assert result.exit_code == 1
        assert "Config error" in result.output
        assert "metrics.fd_mean.bad" in result.output
        assert launched == []

    def test_a_missing_config_file_is_refused(self, launched, tmp_path):
        result = self.run_fmriprep(tmp_path / "nope.json")
        assert result.exit_code == 1
        assert "Config file not found" in result.output
        assert launched == []


class TestConfigExport:

    @pytest.mark.parametrize("pipeline", ["afni", "fmriprep"])
    def test_writes_the_packaged_default(self, tmp_path, pipeline):
        output = tmp_path / "mine.json"

        result = runner.invoke(cli.app, ["config", pipeline, "--output", str(output)])

        assert result.exit_code == 0, result.output
        assert output.read_bytes() == default_config_path(pipeline).read_bytes()
        assert f"--config {output}" in result.output

    def test_refuses_to_overwrite_an_existing_file(self, tmp_path):
        output = tmp_path / "mine.json"
        output.write_text("my edited thresholds")

        result = runner.invoke(cli.app, ["config", "afni", "--output", str(output)])

        assert result.exit_code == 1
        assert "already exists" in result.output and "--force" in result.output
        assert output.read_text() == "my edited thresholds"

    def test_force_overwrites(self, tmp_path):
        output = tmp_path / "mine.json"
        output.write_text("my edited thresholds")

        result = runner.invoke(cli.app, ["config", "afni", "--output", str(output), "--force"])

        assert result.exit_code == 0, result.output
        assert output.read_bytes() == default_config_path("afni").read_bytes()

    def test_a_directory_is_not_a_file_name(self, tmp_path):
        result = runner.invoke(cli.app, ["config", "afni", "--output", str(tmp_path), "--force"])
        assert result.exit_code == 1
        assert "is a directory" in result.output

    def test_missing_parent_directory(self, tmp_path):
        result = runner.invoke(cli.app, ["config", "afni", "--output", str(tmp_path / "no" / "mine.json")])
        assert result.exit_code == 1
        assert "not found" in result.output
