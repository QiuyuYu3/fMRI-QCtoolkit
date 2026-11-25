from pathlib import Path

import pytest
from typer.testing import CliRunner

from fMRI_QCtoolkit import cli
from fMRI_QCtoolkit.dashboard.afni_app import AFNIDashboard
from fMRI_QCtoolkit.dashboard.fmriprep_app import FMRIPrepDashboard

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "example_data" / "fmriprep"
runner = CliRunner()


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "find_free_port", lambda **kwargs: 5123)
    for cls in (AFNIDashboard, FMRIPrepDashboard):
        monkeypatch.setattr(cls, "run", lambda self, **kwargs: calls.append((type(self), kwargs)))
    return calls


def test_dashboard_fmriprep_launches(launched):
    result = runner.invoke(cli.app, ["dashboard", "fmriprep", "--data-file", str(EXAMPLES / "df_final.csv"),
                                     "--task", "rest"])
    assert result.exit_code == 0, result.output
    assert launched == [(FMRIPrepDashboard, {"host": "127.0.0.1", "port": 5123, "debug": False})]


def test_dashboard_afni_launches(launched, tmp_path, sample_afni_data):
    data_file = tmp_path / "df_final.csv"
    sample_afni_data.to_csv(data_file, index=False)

    result = runner.invoke(cli.app, ["dashboard", "afni", "--data-file", str(data_file), "--task", "rest"])
    assert result.exit_code == 0, result.output
    assert [cls for cls, _ in launched] == [AFNIDashboard]


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
