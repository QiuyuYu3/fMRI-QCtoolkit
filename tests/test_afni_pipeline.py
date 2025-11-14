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
        assert len(json_files) == 2
        assert "sub-001" in json_files
        assert "sub-002" in json_files
    
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
        
        assert len(json_files) == 1
        assert "sub-001" in json_files


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
    
    def test_flip_conversion(self, temp_dir, sample_json_data):
        """flip_guess transformation"""
        data_no_flip = sample_json_data.copy()
        data_no_flip["flip guess"] = "NO_FLIP"
        
        qc_dir = temp_dir / "rest_output/QC_sub-001/extra_info"
        qc_dir.mkdir(parents=True)
        (qc_dir / "out.ss_review.sub-001.json").write_text(json.dumps(data_no_flip))
        
        pipeline = AFNIPipeline(temp_dir, "rest", "sub-", temp_dir / "output")
        pipeline._load_raw_data()
        
        assert 'flip_guess' in pipeline.df_raw.columns
        
        pipeline._clean_data()
        
        if 'flip_guess' in pipeline.df_final.columns:
            assert pipeline.df_final['flip_guess'].iloc[0] == 0
        else:
            assert pipeline.df_raw['flip_guess'].iloc[0] == 0
    
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
        lollipop_file = temp_dir / "lollipop_chart_data.csv"
        
        sample_afni_data.to_csv(data_file, index=False)
        
        # create lollipop data
        lollipop_data = pd.DataFrame({
            'ID': ['001', '002'],
            'Variable': ['cens_frac', 'cens_frac'],
            'Value': [0.1, 0.2]
        })
        lollipop_data.to_csv(lollipop_file, index=False)
        
        # Load from saved data
        pipeline = AFNIPipeline.from_saved_data(
            data_file=data_file,
            lollipop_file=lollipop_file,
            task="rest"
        )
        
        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0  # Use flexible assertion for random data