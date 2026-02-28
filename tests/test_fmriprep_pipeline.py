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
        ('sub-101_ses-1_task-rest_run-1_bold', 'rest', 101, 1),
        ('sub-102_ses-1_task-rest_run-2_bold', 'rest', 102, 2),
        ('sub-103_task-rest_run-1_bold', 'rest', 103, 1),
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
        assert pipeline.bold_data['ID'].dtype in ['int64', 'int32']
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