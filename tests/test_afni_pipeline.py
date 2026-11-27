import pytest
import pandas as pd
import json
from fMRI_QCtoolkit.data.afni_pipeline import AFNIPipeline


class TestAFNIPipelineInit:
    
    def test_initialization(self, temp_dir):
        pipeline = AFNIPipeline(
            input_dir=temp_dir,
            task="rest",
            prefix="sub-",
            output_dir=temp_dir / "output"
        )
        
        assert pipeline.task == "rest"
        assert pipeline.prefix == "sub-"
        assert pipeline.input_dir == temp_dir


class TestCleanKey:
    
    def test_removes_spaces(self, temp_dir):
        """Testing removal of spaces"""
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)
        assert pipeline._clean_key("flip guess") == "flip_guess"
    
    def test_removes_parentheses(self, temp_dir):
        """Testing removal of parentheses"""
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)
        assert pipeline._clean_key("global correlation (GCOR)") == "global_correlation_GCOR"
    
    def test_multiple_spaces(self, temp_dir):
        """Test multiple spaces"""
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)
        assert pipeline._clean_key("TRs  total   raw") == "TRs_total_raw"


class TestFindJSONFiles:
    """Testing JSON file search functionality"""
    
    def test_finds_valid_json_files(self, mock_afni_directory):
        pipeline = AFNIPipeline(
            input_dir=mock_afni_directory,
            task="rest",
            prefix="sub-",
            output_dir=mock_afni_directory / "output"
        )
        
        json_files = pipeline._find_json_files()
        assert set(json_files) == {("sub-001", None), ("sub-002", None)}
    
    def test_filters_by_prefix(self, temp_dir, sample_json_data):
        """Testing by prefix filtering"""
        
        valid_qc = temp_dir / "rest_output/QC_sub-001/extra_info"
        invalid_qc = temp_dir / "rest_output/QC_other-999/extra_info"
        
        valid_qc.mkdir(parents=True)
        invalid_qc.mkdir(parents=True)
        
        (valid_qc / "out.ss_review.sub-001.json").write_text(json.dumps(sample_json_data))
        (invalid_qc / "out.ss_review.other-999.json").write_text(json.dumps(sample_json_data))
        
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)
        json_files = pipeline._find_json_files()
        
        assert list(json_files) == [("sub-001", None)]


class TestLoadRawData:
    """Load data"""
    
    def test_loads_json_data(self, mock_afni_directory):
        pipeline = AFNIPipeline(
            input_dir=mock_afni_directory,
            task="rest",
            prefix="sub-",
            output_dir=mock_afni_directory / "output"
        )
        
        pipeline._load_raw_data()
        
        assert pipeline.df_raw is not None
        assert len(pipeline.df_raw) == 2
        assert 'ID' in pipeline.df_raw.columns
    
    def test_handles_missing_files(self, temp_dir):
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)
        
        with pytest.raises(FileNotFoundError):
            pipeline._load_raw_data()


class TestCleanData:
    """Test data cleaning"""
    
    @pytest.mark.parametrize("guess,expected", [("NO_FLIP", 0), ("DO_FLIP", 1)])
    def test_flip_guess_becomes_a_number(self, temp_dir, sample_json_data, guess, expected):
        _qc_dir(temp_dir, "rest_output", "sub-001", {**sample_json_data, "flip guess": guess})

        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()

        assert pipeline.df_final['flip_guess'].iloc[0] == expected

    def test_afni_fields_become_the_dashboard_metrics(self, mock_afni_directory):
        out = mock_afni_directory / "output"
        AFNIPipeline(mock_afni_directory, "rest", "sub-", out).process()

        row = AFNIPipeline.from_saved_data(out / "df_final.csv").df_final.iloc[0]

        assert row[["runs", "TRs_removed", "TRs_total_raw", "cens_mot", "cens_displace", "flip_guess",
                    "DF_frac", "cens_frac", "TSNR", "GCOR"]].tolist() == [2, 4, 300, 0.08, 1.7, 0, 0.71, 0.12,
                                                                          152.3, 0.04]

    def test_every_numeric_field_is_kept(self, temp_dir, sample_json_data):
        # AFNI writes numbers as text
        data = {**sample_json_data, "anat/EPI mask Dice coef": "0.91", "max motion displacement": "1.4",
                "blur estimates (FWHM)": ["5.1", "5.3", "4.9", "5.1"], "AFNI version": "AFNI_24.3.06",
                "slice timing pattern": "alt+z", "vorig rating": "good"}
        qc_dir = temp_dir / "rest_output/QC_sub-001/extra_info"
        qc_dir.mkdir(parents=True)
        (qc_dir / "out.ss_review.sub-001.json").write_text(json.dumps(data))

        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()

        columns = list(pipeline.df_final.columns)
        assert {"anat/EPI_mask_Dice_coef", "max_motion_displacement",
                "blur_estimates_FWHM_1", "blur_estimates_FWHM_4", "flip_guess"} <= set(columns)
        assert not {"AFNI_version", "slice_timing_pattern"} & set(columns)
        assert columns[0] == "ID" and columns[-1] == "vorig_rating"

    def test_removes_prefix_from_id(self, mock_afni_directory):
        """Remove prefix from ID"""
        pipeline = AFNIPipeline(
            mock_afni_directory,
            "rest",
            "sub-",
            mock_afni_directory / "output"
        )
        pipeline._load_raw_data()
        pipeline._clean_data()
        
        # The ID should not contain the sub- prefix.
        assert all(not str(id_).startswith("sub-") for id_ in pipeline.df_final['ID'])


class TestFromSavedData:
    """Test from saved data"""
    
    def test_loads_from_csv(self, temp_dir, sample_afni_data):

        data_file = temp_dir / "df_final.csv"
        sample_afni_data.to_csv(data_file, index=False)

        pipeline = AFNIPipeline.from_saved_data(data_file=data_file, task="rest")

        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0  # Use flexible assertion for random data

    def test_lollipop_keeps_the_afni_variable_list(self, temp_dir, sample_afni_data):
        data_file = temp_dir / "df_final.csv"
        df = sample_afni_data.copy()
        df["flip_guess"] = 0
        df["frac_TRs_cens_1"] = 0.1
        df.to_csv(data_file, index=False)

        lollipop = AFNIPipeline.from_saved_data(data_file=data_file, task="rest").get_lollipop_data()

        assert set(lollipop["Variable"]) == {"cens_frac", "cens_mot", "cens_displace", "TSNR",
                                             "DF_frac", "GCOR", "TRs_total_raw"}

class TestSubjectIdIsABIDSLabel:
    """AFNI keeps IDs as strings through prep; the dashboard's re-read must not undo that."""

    def test_padding_survives_the_round_trip_through_saved_csv(self, temp_dir, sample_afni_data):
        data_file = temp_dir / "df_final.csv"

        df = sample_afni_data.head(2).copy()
        df['ID'] = ['0030', '090']
        df.to_csv(data_file, index=False)

        pipeline = AFNIPipeline.from_saved_data(data_file=data_file, task="rest")

        assert list(pipeline.df_final['ID']) == ['0030', '090']
        assert pipeline.get_lollipop_data()['ID'].unique().tolist() == ['0030', '090']


def _qc_dir(root, rel, subject_id, data):
    info = root / rel / f"QC_{subject_id}" / "extra_info"
    info.mkdir(parents=True)
    (info / f"out.ss_review.{subject_id}.json").write_text(json.dumps(data))


class TestSubjectMatching:

    def test_sessions_come_from_the_folders(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "sub-001/ses-01/rest_output", "sub-001", sample_json_data)
        _qc_dir(temp_dir, "sub-001/ses-02/rest_output", "sub-001", sample_json_data)
        json_files = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)._find_json_files()
        assert sorted(json_files) == [("sub-001", "01"), ("sub-001", "02")]
        assert "ses-02" in json_files[("sub-001", "02")].as_posix()

    def test_sessions_come_from_the_subject_id(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "rest_output", "sub-001_ses-pre", sample_json_data)
        _qc_dir(temp_dir, "rest_output", "sub-001_ses-post", sample_json_data)
        json_files = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)._find_json_files()
        assert sorted(json_files) == [("sub-001", "post"), ("sub-001", "pre")]

    def test_narrowing_task_to_a_session_keeps_one(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "ses-01/rest_output", "sub-001", sample_json_data)
        _qc_dir(temp_dir, "ses-02/rest_output", "sub-001", sample_json_data)
        json_files = AFNIPipeline(temp_dir, "ses-02/rest", "sub-", temp_dir)._find_json_files()
        assert list(json_files) == [("sub-001", "02")]

    def test_two_folders_for_one_participant_and_session_are_refused(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "ses-01/rest_output", "sub-001", sample_json_data)
        _qc_dir(temp_dir, "ses-01/rest2_output", "sub-001", sample_json_data)
        _qc_dir(temp_dir, "ses-01/rest_output", "sub-002", sample_json_data)
        with pytest.raises(ValueError, match=r"sub-001 session 01: .*rest.*\n.*Narrow --task"):
            AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)._find_json_files()

    def test_alphanumeric_labels_match_the_prefix(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "rest_output", "sub-A01", sample_json_data)
        assert list(AFNIPipeline(temp_dir, "rest", "sub-", temp_dir)._find_json_files()) == [("sub-A01", None)]

    def test_prefix_is_matched_literally(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "rest_output", "s.001", sample_json_data)
        _qc_dir(temp_dir, "rest_output", "sX001", sample_json_data)
        assert list(AFNIPipeline(temp_dir, "rest", "s.", temp_dir)._find_json_files()) == [("s.001", None)]

    def test_prep_reports_duplicates_without_a_traceback(self, temp_dir, sample_json_data):
        from typer.testing import CliRunner
        from fMRI_QCtoolkit.cli import app

        _qc_dir(temp_dir, "rest_output", "sub-001", sample_json_data)
        _qc_dir(temp_dir, "rest2_output", "sub-001", sample_json_data)
        result = CliRunner().invoke(app, ["prep", "afni", "--input-dir", str(temp_dir), "--output-dir",
                                          str(temp_dir / "out"), "--task", "rest", "--prefix", "sub-"])

        assert result.exit_code == 1
        assert "Narrow --task" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestSessionsAndLists:

    @staticmethod
    def _process(root):
        return AFNIPipeline(root, "rest", "sub-", root / "out").process().df_final

    def test_one_row_per_participant_and_session(self, temp_dir, sample_json_data):
        for subject, session in (("sub-002", "02"), ("sub-010", "01"), ("sub-002", "01")):
            _qc_dir(temp_dir, f"{subject}/ses-{session}/rest_output", subject, sample_json_data)
        df = self._process(temp_dir)
        assert list(df.columns[:2]) == ["ID", "session"]
        assert list(zip(df["ID"], df["session"])) == [("002", "01"), ("002", "02"), ("010", "01")]

    def test_single_session_data_has_no_session_column(self, mock_afni_directory):
        assert "session" not in self._process(mock_afni_directory).columns

    def test_a_field_with_several_values_anywhere_is_numbered_everywhere(self, temp_dir, sample_json_data):
        _qc_dir(temp_dir, "rest_output", "sub-001", {**sample_json_data, "num TRs per run": "160",
                                                      "fraction TRs censored": "0.050"})
        _qc_dir(temp_dir, "rest_output", "sub-002", {**sample_json_data, "num TRs per run": ["160", "158"],
                                                      "fraction TRs censored": "0.100"})
        df = self._process(temp_dir)
        assert "num_TRs_per_run" not in df.columns
        assert df["num_TRs_per_run_1"].tolist() == ["160", "160"]
        assert df["num_TRs_per_run_2"].isna().tolist() == [True, False]
        assert df["frac_TRs_cens_1"].tolist() == ["0.050", "0.100"]
