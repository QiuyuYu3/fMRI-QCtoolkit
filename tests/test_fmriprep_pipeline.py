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
        required_cols = ['ID', 'run', 'session', 'modality']
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
        assert all(pipeline.bold_data['modality'] == 'rest')


class TestLoadRatingData:
    
    def test_loads_task_specific_csv(self, temp_dir, random_bold_data, random_rating_data):
        """Test loading task-specific rating data with random data"""
        bold_file, rating_dir = setup_fmriprep_env(
            temp_dir, random_bold_data, random_rating_data
        )
        
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_rating_data()
        
        assert pipeline.rating_data is not None
        assert 'ID' in pipeline.rating_data.columns
        assert 'run' in pipeline.rating_data.columns
    
    def test_loads_task_specific_csv_random(self, temp_dir, random_bold_data, random_rating_data):
        """Test with random rating data"""
        bold_file, rating_dir = setup_fmriprep_env(temp_dir, random_bold_data, random_rating_data)
        
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_rating_data()
        
        assert pipeline.rating_data is not None
        assert len(pipeline.rating_data) > 0


class TestCleanData:
    """Test data cleaning and merging"""
    
    def test_merges_bold_and_rating(self, temp_dir, random_bold_data, random_rating_data):
        """Use random data from conftest"""
        bold_file, rating_dir = setup_fmriprep_env(
            temp_dir, random_bold_data, random_rating_data
        )
        
        pipeline = FMRIPrepPipeline(bold_file, rating_dir, "rest", temp_dir / "output")
        pipeline._load_raw_data()
        pipeline._clean_data()
        
        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0


class TestFromSavedData:
    
    def test_loads_from_csv(self, temp_dir, sample_fmriprep_data):
        """Test loading from saved CSV"""
        data_file = temp_dir / "df_final.csv"
        lollipop_file = temp_dir / "lollipop_chart_data.csv"
        
        sample_fmriprep_data.to_csv(data_file, index=False)
        
        # Create matching lollipop data
        lollipop_data = pd.DataFrame({
            'ID': sample_fmriprep_data['ID'].head(2).values,
            'Variable': ['fd_perc', 'fd_perc'],
            'Value': sample_fmriprep_data['fd_perc'].head(2).values
        })
        lollipop_data.to_csv(lollipop_file, index=False)
        
        pipeline = FMRIPrepPipeline.from_saved_data(
            data_file=data_file,
            lollipop_file=lollipop_file,
            task="rest"
        )
        
        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0
        assert pipeline.task == "rest"


class TestIntegrationWithExampleData:
    """Integration tests using example data"""
    
    def test_from_saved_data(self, fmriprep_examples: Path):
        """Test loading from example data files"""
        data_file = fmriprep_examples / "df_final.csv"
        lollipop_file = fmriprep_examples / "lollipop_chart_data.csv"

        assert data_file.exists(), "Missing df_final.csv"
        assert lollipop_file.exists(), "Missing lollipop_chart_data.csv"

        pipeline = FMRIPrepPipeline.from_saved_data(
            data_file=data_file,
            lollipop_file=lollipop_file,
            task="rest",
        )

        df = pipeline.get_data()
        lol = pipeline.get_lollipop_data()

        assert isinstance(df, pd.DataFrame) and not df.empty
        assert isinstance(lol, pd.DataFrame) and not lol.empty
        assert {"ID", "run"}.issubset(df.columns)
        assert {"ID", "Variable", "Value"}.issubset(lol.columns)

    def test_process_end_to_end(self, fmriprep_examples: Path, examples_root: Path, tmp_path: Path):
        """Test complete processing pipeline"""
        bold_file = fmriprep_examples / "group_bold.tsv"
        rating_dir = examples_root / "random_data" / "fmriprep_rating"

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
        df_path = out_dir / "df_final.csv"
        lol_path = out_dir / "lollipop_chart_data.csv"
        assert df_path.exists() and lol_path.exists()

        # Verify data quality
        df = pd.read_csv(df_path)
        lol = pd.read_csv(lol_path)
        assert not df.empty and not lol.empty
        assert {"ID", "run"}.issubset(df.columns)
        assert {"ID", "Variable", "Value"}.issubset(lol.columns)

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

    def test_padding_survives_the_round_trip_through_saved_csv(self, temp_dir,
                                                               sample_fmriprep_data):
        """qc dash re-reads df_final.csv, so the zeros have to survive that read too."""
        data_file = temp_dir / "df_final.csv"
        lollipop_file = temp_dir / "lollipop_chart_data.csv"

        df = sample_fmriprep_data.head(2).copy()
        df['ID'] = ['0030', '090']
        df.to_csv(data_file, index=False)
        pd.DataFrame({
            'ID': ['0030', '090'],
            'Variable': ['fd_perc', 'fd_perc'],
            'Value': df['fd_perc'].values,
        }).to_csv(lollipop_file, index=False)

        pipeline = FMRIPrepPipeline.from_saved_data(
            data_file=data_file, lollipop_file=lollipop_file, task="rest"
        )

        assert list(pipeline.df_final['ID']) == ['0030', '090']
        assert list(pipeline.lollipop_chart_data['ID']) == ['0030', '090']
