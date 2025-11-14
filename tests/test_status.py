import pytest
import pandas as pd
import numpy as np
from fMRI_QCtoolkit.utils.status import (
    assign_afni_status,
    assign_fmriprep_status,
    get_status_mapping,
    get_status_colors
)


class TestAFNIStatus:
    """AFNI status assignment tests - using parametrize to reduce duplication"""
    
    @pytest.mark.parametrize("value,variable,expected", [
        # DF_frac: good > 0.7, other 0.6-0.7, bad <= 0.6
        (0.8, "DF_frac", "good"),
        (0.71, "DF_frac", "good"),
        (0.65, "DF_frac", "other"),
        (0.61, "DF_frac", "other"),
        (0.5, "DF_frac", "bad"),
        (0.6, "DF_frac", "bad"),
        
        # cens_frac: good < 0.15, other 0.15-0.2, bad >= 0.2
        (0.1, "cens_frac", "good"),
        (0.14, "cens_frac", "good"),
        (0.17, "cens_frac", "other"),
        (0.15, "cens_frac", "other"),
        (0.25, "cens_frac", "bad"),
        (0.2, "cens_frac", "bad"),
        
        # cens_mot: good < 0.1, other 0.1-0.15, bad >= 0.15
        (0.08, "cens_mot", "good"),
        (0.12, "cens_mot", "other"),
        (0.16, "cens_mot", "bad"),
        
        # cens_displace: good < 6, other 6-8, bad >= 8
        (4.5, "cens_displace", "good"),
        (7.0, "cens_displace", "other"),
        (10.0, "cens_displace", "bad"),
        
        # GCOR: good < 0.15, other 0.15-0.2, bad >= 0.2
        (0.12, "GCOR", "good"),
        (0.17, "GCOR", "other"),
        (0.22, "GCOR", "bad"),
        
        # flip_guess: good = 0, bad != 0
        (0, "flip_guess", "good"),
        (1, "flip_guess", "bad"),
        
        # TSNR: good > 150, other <= 150
        (200, "TSNR", "good"),
        (140, "TSNR", "other"),
        
        # NA handling
        (pd.NA, "DF_frac", "NA"),
        (None, "DF_frac", "NA"),
        (np.nan, "cens_frac", "NA"),
        
        # Unknown variable defaults to "other"
        (100, "unknown_var", "other"),
    ])
    def test_afni_status_assignment(self, value, variable, expected):
        """Test AFNI status assignment for various variables and values"""
        assert assign_afni_status(value, variable) == expected


class TestFMRIPrepStatus:
    """fMRIPrep status assignment tests"""
    
    @pytest.mark.parametrize("value,variable,expected", [
        # fd_perc: good <= 15, other 15-20, bad > 20
        (10, "fd_perc", "good"),
        (15, "fd_perc", "good"),
        (18, "fd_perc", "other"),
        (20, "fd_perc", "other"),
        (25, "fd_perc", "bad"),
        
        # fd_mean: good < 0.2, other 0.2-0.3, bad >= 0.3
        (0.15, "fd_mean", "good"),
        (0.25, "fd_mean", "other"),
        (0.35, "fd_mean", "bad"),
        
        # gcor: good < 0.15, other 0.15-0.2, bad >= 0.2
        (0.12, "gcor", "good"),
        (0.17, "gcor", "other"),
        (0.22, "gcor", "bad"),
        
        # tsnr: good > 150, other <= 150
        (200, "tsnr", "good"),
        (140, "tsnr", "other"),
        
        # NA handling
        (None, "fd_perc", "NA"),
        (np.nan, "gcor", "NA"),
    ])
    def test_fmriprep_status_assignment(self, value, variable, expected):
        """Test fMRIPrep status assignment for various variables and values"""
        assert assign_fmriprep_status(value, variable) == expected


class TestStatusHelpers:
    """Test helper functions for status mappings and colors"""
    
    def test_status_mapping(self):
        """Test status mapping returns correct indices"""
        mapping = get_status_mapping()
        assert mapping['NA'] == 0
        assert mapping['bad'] == 1
        assert mapping['other'] == 2
        assert mapping['good'] == 3
    
    def test_status_colors(self):
        """Test status colors are properly defined"""
        colors = get_status_colors()
        assert 0 in colors  # NA
        assert 1 in colors  # bad
        assert 2 in colors  # other
        assert 3 in colors  # good
        assert all(c.startswith('#') for c in colors.values())
    
    def test_colors_match_mapping(self):
        """Ensure color keys align with mapping values"""
        mapping = get_status_mapping()
        colors = get_status_colors()
        
        for label, idx in mapping.items():
            assert idx in colors, f"Missing color for {label} (index {idx})"


class TestStatusWithRandomData:
    """Test status assignment with randomly generated data"""
    
    def test_afni_df_frac_random(self, random_values):
        """Test DF_frac with random values"""
        for value in random_values['df_frac_values']:
            result = assign_afni_status(value, "DF_frac")
            if value > 0.7:
                assert result == "good"
            elif value > 0.6:
                assert result == "other"
            else:
                assert result == "bad"
    
    def test_afni_cens_frac_random(self, random_values):
        """Test cens_frac with random values"""
        for value in random_values['cens_frac_values']:
            result = assign_afni_status(value, "cens_frac")
            if value >= 0.2:
                assert result == "bad"
            elif value >= 0.15:
                assert result == "other"
            else:
                assert result == "good"
    
    def test_fmriprep_gcor_random(self, random_values):
        """Test gcor with random values"""
        for value in random_values['gcor_values']:
            result = assign_fmriprep_status(value, "gcor")
            if value >= 0.2:
                assert result == "bad"
            elif value >= 0.15:
                assert result == "other"
            else:
                assert result == "good"
    
    def test_fmriprep_fd_perc_random(self, random_values):
        """Test fd_perc with random values"""
        for value in random_values['fd_perc_values']:
            result = assign_fmriprep_status(value, "fd_perc")
            if value > 20:
                assert result == "bad"
            elif value > 15:
                assert result == "other"
            else:
                assert result == "good"


@pytest.fixture()
def random_values():
    """Generate random test values for status testing"""
    np.random.seed(42)
    return {
        'df_frac_values': np.random.uniform(0.3, 0.9, 20),
        'cens_frac_values': np.random.uniform(0.05, 0.3, 20),
        'cens_mot_values': np.random.uniform(0.02, 0.25, 20),
        'cens_displace_values': np.random.uniform(2, 15, 20),
        'gcor_values': np.random.uniform(0.05, 0.35, 20),
        'tsnr_values': np.random.uniform(80, 350, 20),
        'fd_perc_values': np.random.uniform(3, 35, 20),
        'fd_mean_values': np.random.uniform(0.05, 0.45, 20),
    }