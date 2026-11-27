import pytest
import pandas as pd
from pathlib import Path
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline


def create_rating_files(rating_dir, rating_data, task="rest"):
    """Helper: Create rating CSV files"""
    for _, row in rating_data.iterrows():
        subject_id = row['ID']
        filename = f"sub-{subject_id}_{task}.csv"
        (rating_dir / filename).write_text(row.to_frame().T.to_csv(index=False))


def setup_fmriprep_env(temp_dir, bold_data, rating_data=None, task="rest"):
    """Helper: Setup complete fMRIPrep test environment
    
    Args:
        temp_dir: Temporary directory path
        bold_data: DataFrame with BOLD data
        rating_data: Optional DataFrame with rating data
        task: Task name for rating files (default: "rest")
    
    Returns:
        tuple: (bold_file path, rating_dir path)
    """
    bold_file = temp_dir / "group_bold.tsv"
    rating_dir = temp_dir / "ratings"
    rating_dir.mkdir(exist_ok=True)
    
    bold_data.to_csv(bold_file, sep='\t', index=False)
    
    if rating_data is not None:
        create_rating_files(rating_dir, rating_data, task)
    
    return bold_file, rating_dir


class TestFMRIPrepPipelineInit:
    
    def test_initialization(self, temp_dir, random_bold_data):
        """Test basic initialization with random BOLD data"""
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        
        pipeline = FMRIPrepPipeline(
            bold_file=bold_file,
            rating_dir=rating_dir,
            task="rest",
            output_dir=temp_dir / "output"
        )
        
        assert pipeline.task == "rest"
        assert pipeline.bold_file == bold_file


class TestLoadBoldData:
    
    @pytest.mark.parametrize("bids_name,task,expected_id,expected_run", [
        ('sub-101_ses-1_task-rest_run-1_bold', 'rest', '101', 1),
        ('sub-102_ses-1_task-rest_run-2_bold', 'rest', '102', 2),
        ('sub-103_task-rest_run-1_bold', 'rest', '103', 1),
    ])
    def test_parses_bids_name(self, temp_dir, random_bold_data, bids_name, task, expected_id, expected_run):
        """Test BIDS name parsing - use first row from random data, override bids_name"""
        bold_data = random_bold_data.head(1).copy()
        bold_data['bids_name'] = bids_name
        
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, bold_data, task=task)
        
        pipeline = FMRIPrepPipeline(
            bold_file=bold_file,
            rating_dir=rating_dir,
            task=task,
            output_dir=temp_dir / "output"
        )
        pipeline._load_bold_data()
        
        assert expected_id in pipeline.bold_data['ID'].values
        assert expected_run in pipeline.bold_data['run'].values
    
    def test_parses_bids_name_batch(self, temp_dir, random_bold_data):
        """Batch test BIDS parsing with random data"""
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()
        
        # Verify required columns
        required_cols = ['ID', 'run', 'session', 'task']
        assert all(col in pipeline.bold_data.columns for col in required_cols)
        
        # Verify data types
        # ID is a BIDS label, kept as a string so zero-padding survives
        assert pd.api.types.is_string_dtype(pipeline.bold_data['ID'])
        assert pipeline.bold_data['run'].dtype in ['int64', 'int32']
    
    def test_filters_by_task(self, temp_dir, random_bold_data):
        """Test task filtering - use random data, modify tasks"""
        bold_data = random_bold_data.head(3).copy()
        bold_data['bids_name'] = [
            'sub-101_task-rest_bold',
            'sub-102_task-task1_bold',
            'sub-103_task-rest_bold'
        ]
        
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, bold_data)
        
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()
        
        assert len(pipeline.bold_data) == 2
        assert all(pipeline.bold_data['task'] == 'rest')


class TestLoadRatingData:
    
    def test_loads_task_specific_csv(self, temp_dir, random_bold_data, random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(
            temp_dir, random_bold_data, random_rating_data
        )
        (rating_dir / "sub-X01_ses-1_nback.csv").write_text("ID,Final_1_r\nX01,good\n")

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_rating_data()

        assert sorted(pipeline.rating_data['ID']) == sorted(random_rating_data['ID'].astype(str))
        assert (pipeline.rating_data['run'] == 1).all()

    def test_another_tasks_ratings_are_never_used(self, temp_dir, random_bold_data, random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data, random_rating_data)
        (rating_dir / "sub-001_ses-1_nback_dir-AP.csv").write_text("ID\n001\n")
        (rating_dir / "sub-001.csv").write_text("ID\n001\n")
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "stopsignal", temp_dir / "output")
        with pytest.raises(FileNotFoundError, match="No rating files for task stopsignal .*; it has ratings for: nback, rest$"):
            pipeline._load_rating_data()

    def test_an_empty_folder_lists_no_tasks(self, temp_dir, random_bold_data):
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        with pytest.raises(FileNotFoundError) as error:
            pipeline._load_rating_data()
        assert "it has ratings for" not in str(error.value)


class TestCleanData:
    """Test data cleaning and merging"""
    
    def test_names_without_session_or_run_match_the_rating_files(self, temp_dir):
        # The rating page names such files sub-<ID>_<task>.csv and their columns <module>_1_r
        bold_file = temp_dir / "group_bold.tsv"
        bold_file.write_text("bids_name\tfd_mean\nsub-01_task-rest_bold\t0.1\nsub-02_task-rest_bold\t0.2\n")
        rating_dir = temp_dir / "ratings"
        rating_dir.mkdir()
        (rating_dir / "sub-01_rest.csv").write_text("ID,T1mask_1_r,Final_1_r\n01,good,bad\n")
        (rating_dir / "sub-02_rest.csv").write_text("ID,T1mask_1_r,Final_1_r\n02,other,good\n")

        df = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output").process().df_final

        assert df[['ID', 'session', 'run', 'fd_mean', 'T1mask', 'Final']].values.tolist() == [
            ['01', '1', 1, 0.1, 'good', 'bad'], ['02', '1', 1, 0.2, 'other', 'good']]


class TestFromSavedData:
    
    def test_loads_from_csv(self, temp_dir, sample_fmriprep_data):
        """Test loading from saved CSV"""
        data_file = temp_dir / "df_final.csv"
        sample_fmriprep_data.to_csv(data_file, index=False)

        pipeline = FMRIPrepPipeline.from_saved_data(data_file=data_file, task="rest")

        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0
        assert pipeline.task == "rest"
        assert set(pipeline.get_lollipop_data()["Variable"]) == {
            "fd_perc", "fd_mean", "gcor", "gsr_x", "gsr_y", "aor", "aqi", "dvars_nstd", "tsnr"}

    def test_session_labels_stay_strings(self, temp_dir):
        data_file = temp_dir / "df_final.csv"
        data_file.write_text("ID,session,run,fd_mean\n001,01,1,0.1\n002,pre,1,0.2\n003,,1,0.3\n")

        pipeline = FMRIPrepPipeline.from_saved_data(data_file=data_file)

        assert pipeline.df_final['session'].tolist()[:2] == ['01', 'pre']
        assert pipeline.get_lollipop_data()['session'].tolist()[:2] == ['01', 'pre']

    def test_a_metric_that_never_varies_sits_at_zero(self, temp_dir):
        data_file = temp_dir / "df_final.csv"
        data_file.write_text("ID,session,run,fd_mean,tsnr\n001,01,1,0.1,135\n002,01,1,0.3,135\n003,01,1,,135\n")

        lol = FMRIPrepPipeline.from_saved_data(data_file=data_file).get_lollipop_data()

        assert lol.loc[lol["Variable"] == "tsnr", "Value"].tolist() == [0.0, 0.0, 0.0]
        assert lol.loc[lol["Variable"] == "fd_mean", "Value"].tolist()[:2] == [-0.707, 0.707]

    def test_table_without_metrics_gives_an_empty_lollipop(self, temp_dir):
        data_file = temp_dir / "df_final.csv"
        data_file.write_text("ID,session,run\n001,01,1\n")

        assert FMRIPrepPipeline.from_saved_data(data_file=data_file).get_lollipop_data().empty


class TestIntegrationWithExampleData:
    """Integration tests using example data"""
    
    def test_from_saved_data(self, fmriprep_examples: Path):
        """Test loading from example data files"""
        data_file = fmriprep_examples / "df_final.csv"
        assert data_file.exists(), "Missing df_final.csv"

        pipeline = FMRIPrepPipeline.from_saved_data(data_file=data_file, task="rest")

        df = pipeline.get_data()
        lol = pipeline.get_lollipop_data()

        assert isinstance(df, pd.DataFrame) and not df.empty
        assert isinstance(lol, pd.DataFrame) and not lol.empty
        assert {"ID", "run"}.issubset(df.columns)
        assert {"ID", "Variable", "Value"}.issubset(lol.columns)

    def test_process_end_to_end(self, fmriprep_examples: Path, tmp_path: Path):
        """Test complete processing pipeline"""
        bold_file = fmriprep_examples / "group_bold.tsv"
        rating_dir = fmriprep_examples / "ratings"

        assert bold_file.exists(), "Missing group_bold.tsv"
        assert rating_dir.exists(), "Missing rating directory"

        out_dir = tmp_path / "out"

        pipeline = FMRIPrepPipeline(
            bold_file=bold_file,
            rating_dir=rating_dir,
            task="rest",
            output_dir=out_dir,
        )
        pipeline.process()

        # Verify output files
        assert sorted(p.name for p in out_dir.iterdir()) == ["df_final.csv"]

        # Verify data quality
        df = pd.read_csv(out_dir / "df_final.csv")
        lol = pipeline.get_lollipop_data()
        assert not df.empty and not lol.empty
        assert {"ID", "run"}.issubset(df.columns)
        assert {"ID", "Variable", "Value"}.issubset(lol.columns)
        # Every run of the example has both its MRIQC metrics and its ratings
        assert len(df) == 15
        assert df["Final"].notna().all() and df["gcor"].notna().all()
        # Rated once per session, in the run 1 columns, and given to every run
        assert df[["T1mask", "Norm", "SurfRecon"]].notna().all().all()

class TestNonNumericSessionLabels:
    """BIDS session labels need not be numeric (ses-pre, ses-V1)."""

    @pytest.mark.parametrize("bids_name,expected_session", [
        ('sub-101_ses-01_task-rest_run-1_bold', '01'),
        ('sub-101_ses-pre_task-rest_run-1_bold', 'pre'),
        ('sub-101_ses-V1_task-rest_run-1_bold', 'V1'),
        ('sub-101_task-rest_run-1_bold', '1'),
    ])
    def test_bold_session_is_read_as_a_label(self, temp_dir, random_bold_data,
                                             bids_name, expected_session):
        bold_data = random_bold_data.head(1).copy()
        bold_data['bids_name'] = bids_name

        bold_file, rating_dir = setup_fmriprep_env(temp_dir, bold_data)
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()

        assert pipeline.bold_data['session'].iloc[0] == expected_session

    def test_rating_session_is_read_as_a_label(self, temp_dir, random_bold_data,
                                               random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        row = random_rating_data.head(1)
        (rating_dir / "sub-101_ses-pre_rest.csv").write_text(row.to_csv(index=False))

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_rating_data()

        assert pipeline.rating_data['session'].iloc[0] == 'pre'

    def test_both_sides_share_a_dtype_so_the_merge_holds(self, temp_dir, random_bold_data,
                                                        random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(
            temp_dir, random_bold_data, random_rating_data
        )

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()

        assert pipeline.bold_data['session'].dtype == pipeline.rating_data['session'].dtype


class TestSubjectIdIsABIDSLabel:
    """ID is a BIDS label, not a number: zero-padding is significant and non-numeric is legal."""

    def _bold(self, random_bold_data, bids_names):
        rows = [random_bold_data.head(1).copy().assign(bids_name=n) for n in bids_names]
        return pd.concat(rows, ignore_index=True)

    def test_padded_and_unpadded_ids_stay_distinct(self, temp_dir, random_bold_data):
        """sub-0030 and sub-30 are different people; as ints they silently merge into one."""
        bold_data = self._bold(random_bold_data, [
            'sub-0030_ses-1_task-rest_run-1_bold',
            'sub-30_ses-1_task-rest_run-1_bold',
            'sub-090_ses-1_task-rest_run-1_bold',
            'sub-90_ses-1_task-rest_run-1_bold',
        ])
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, bold_data)

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()

        assert sorted(pipeline.bold_data['ID']) == ['0030', '090', '30', '90']

    def test_non_numeric_id_does_not_crash(self, temp_dir, random_bold_data):
        bold_data = self._bold(random_bold_data, ['sub-A01_ses-1_task-rest_run-1_bold'])
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, bold_data)

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()

        assert pipeline.bold_data['ID'].iloc[0] == 'A01'

    def test_rating_csv_keeps_leading_zeros(self, temp_dir, random_bold_data, random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        row = random_rating_data.head(1).copy()
        row['ID'] = '0030'
        (rating_dir / "sub-0030_ses-01_rest.csv").write_text(row.to_csv(index=False))

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_rating_data()

        assert pipeline.rating_data['ID'].iloc[0] == '0030'

    def test_both_sides_share_a_dtype_so_the_merge_holds(self, temp_dir, random_bold_data,
                                                         random_rating_data):
        bold_file, rating_dir = setup_fmriprep_env(
            temp_dir, random_bold_data, random_rating_data
        )

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()

        assert pipeline.bold_data['ID'].dtype == pipeline.rating_data['ID'].dtype

    def test_ids_sort_numerically_not_lexicographically(self):
        pipeline = FMRIPrepPipeline.__new__(FMRIPrepPipeline)
        pipeline.df_final = pd.DataFrame({'ID': ['9', '10', '0030', 'A01', '2']})

        pipeline._sort_by_id()

        assert list(pipeline.df_final['ID']) == ['2', '9', '10', '0030', 'A01']

    def test_padding_survives_the_round_trip_through_saved_csv(self, temp_dir,
                                                               sample_fmriprep_data):
        """qc dash re-reads df_final.csv, so the zeros have to survive that read too."""
        data_file = temp_dir / "df_final.csv"

        df = sample_fmriprep_data.head(2).copy()
        df['ID'] = ['0030', '090']
        df.to_csv(data_file, index=False)

        pipeline = FMRIPrepPipeline.from_saved_data(data_file=data_file, task="rest")

        assert list(pipeline.df_final['ID']) == ['0030', '090']
        assert pipeline.get_lollipop_data()['ID'].unique().tolist() == ['0030', '090']


class TestMergeMismatchIsReported:
    """A key mismatch leaves every row half-empty; the row count alone never shows it."""

    def _env(self, temp_dir, bold_bids_name, rating_filename, rating_row):
        bold_data = pd.DataFrame([{
            'bids_name': bold_bids_name, 'fd_perc': 10.0, 'gcor': 0.2, 'dummy_trs': 4,
            'gsr_x': 0.02, 'gsr_y': 0.02, 'aor': 0.2, 'aqi': 0.5, 'dvars_nstd': 1.0,
            'tsnr': 150.0, 'fd_mean': 0.2, 'spacing_tr': 2.0,
        }])
        bold_file = temp_dir / "group_bold.tsv"
        rating_dir = temp_dir / "ratings"
        rating_dir.mkdir(exist_ok=True)
        bold_data.to_csv(bold_file, sep='\t', index=False)
        (rating_dir / rating_filename).write_text(pd.DataFrame([rating_row]).to_csv(index=False))
        return bold_file, rating_dir

    def test_session_label_mismatch_is_reported(self, temp_dir, capsys):
        """ses-1 in MRIQC vs ses-01 in the ratings: 2 rows out, 0 of them joined."""
        bold_file, rating_dir = self._env(
            temp_dir, 'sub-101_ses-1_task-rest_run-1_bold',
            'sub-101_ses-01_rest.csv', {'ID': '101', 'Final_1_r': 'good'},
        )

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()

        out = capsys.readouterr().out
        assert "0 matched" in out
        assert "no record matched" in out
        assert "session: rating=['01'] vs BOLD=['1']" in out

    def test_matching_labels_stay_quiet(self, temp_dir, capsys):
        bold_file, rating_dir = self._env(
            temp_dir, 'sub-101_ses-01_task-rest_run-1_bold',
            'sub-101_ses-01_rest.csv', {'ID': '101', 'Final_1_r': 'good'},
        )

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()

        out = capsys.readouterr().out
        assert "1 matched" in out
        assert "no record matched" not in out

    def test_every_numeric_iqm_is_kept(self, temp_dir):
        bold_file, rating_dir = self._env(
            temp_dir, 'sub-101_ses-01_task-rest_run-1_bold',
            'sub-101_ses-01_rest.csv', {'ID': '101', 'Final_1_r': 'good'},
        )
        bold = pd.read_csv(bold_file, sep='	').assign(efc=0.5, snr=3.2, provenance="mriqc 24")
        bold.to_csv(bold_file, sep='	', index=False)

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_bold_data()

        assert {'efc', 'snr', 'fd_perc', 'spacing_tr'} <= set(pipeline.bold_data.columns)
        assert not {'provenance', 'bids_name'} & set(pipeline.bold_data.columns)

    def test_merge_indicator_is_not_left_in_the_output(self, temp_dir):
        bold_file, rating_dir = self._env(
            temp_dir, 'sub-101_ses-01_task-rest_run-1_bold',
            'sub-101_ses-01_rest.csv', {'ID': '101', 'Final_1_r': 'good'},
        )

        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()

        assert '_merge' not in pipeline.df_final.columns


class TestT1wMetrics:
    """group_T1w.tsv adds the anatomical IQMs to every run of the participant (and session) they belong to."""

    @staticmethod
    def _env(temp_dir, bold_names, t1w_rows):
        bold = pd.DataFrame({'bids_name': bold_names, 'fd_mean': 0.1, 'efc': 0.4})
        bold_file = temp_dir / "group_bold.tsv"
        bold.to_csv(bold_file, sep='\t', index=False)
        rating_dir = temp_dir / "ratings"
        rating_dir.mkdir(exist_ok=True)
        (rating_dir / "sub-01_ses-01_rest.csv").write_text("ID,Final_1_r\n01,good\n")
        t1w_file = temp_dir / "group_T1w.tsv"
        pd.DataFrame(t1w_rows, columns=['bids_name', 'cjv', 'efc']).to_csv(t1w_file, sep='\t', index=False)
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "out", t1w_file=t1w_file)
        pipeline._load_raw_data()
        pipeline._clean_data()
        return pipeline.df_final.set_index(['ID', 'session', 'run'])

    def test_a_session_less_t1w_reaches_every_session(self, temp_dir):
        df = self._env(temp_dir, ['sub-01_ses-01_task-rest_run-1_bold', 'sub-01_ses-02_task-rest_run-2_bold'],
                       [['sub-01_T1w', 0.4, 0.5]])
        assert df['t1w_cjv'].tolist() == [0.4, 0.4]
        assert df['efc'].tolist() == [0.4, 0.4] and df['t1w_efc'].tolist() == [0.5, 0.5]

    def test_each_session_gets_its_own_t1w(self, temp_dir):
        df = self._env(temp_dir, ['sub-01_ses-01_task-rest_run-1_bold', 'sub-01_ses-02_task-rest_run-1_bold',
                                  'sub-02_ses-01_task-rest_run-1_bold'],
                       [['sub-01_ses-01_T1w', 0.4, 0.5], ['sub-01_ses-02_T1w', 0.6, 0.7], ['sub-02_T1w', 0.8, 0.9]])
        assert df.loc[('01', '01', 1), 't1w_cjv'] == 0.4
        assert df.loc[('01', '02', 1), 't1w_cjv'] == 0.6
        assert df.loc[('02', '01', 1), 't1w_cjv'] == 0.8

    def test_several_t1w_in_one_session_are_left_empty(self, temp_dir, capsys):
        df = self._env(temp_dir, ['sub-01_ses-01_task-rest_run-1_bold', 'sub-02_ses-01_task-rest_run-1_bold'],
                       [['sub-01_ses-01_run-1_T1w', 0.4, 0.5], ['sub-01_ses-01_run-2_T1w', 0.6, 0.7],
                        ['sub-02_ses-01_T1w', 0.8, 0.9]])
        assert pd.isna(df.loc[('01', '01', 1), 't1w_cjv'])
        assert df.loc[('02', '01', 1), 't1w_cjv'] == 0.8
        assert "sub-01 session 01 has 2 T1w images" in capsys.readouterr().out

    def test_without_the_option_nothing_changes(self, temp_dir, random_bold_data):
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data)
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "out")
        pipeline._load_bold_data()
        assert pipeline.t1w_data is None

    def test_cli_rejects_a_missing_t1w_file(self, temp_dir):
        from typer.testing import CliRunner
        from fMRI_QCtoolkit.cli import app
        bold_file = temp_dir / "group_bold.tsv"
        bold_file.write_text("bids_name\tfd_mean\nsub-01_task-rest_bold\t0.1\n")
        (temp_dir / "ratings").mkdir()
        result = CliRunner().invoke(app, ["prep", "fmriprep", "--bold-file", str(bold_file), "--rating-dir",
                                          str(temp_dir / "ratings"), "--task", "rest", "--output-dir",
                                          str(temp_dir / "out"), "--t1w-file", str(temp_dir / "nope.tsv")])
        assert result.exit_code == 1
        assert "T1w file not found" in result.output
