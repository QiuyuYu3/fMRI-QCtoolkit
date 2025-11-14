import pytest
import numpy as np
from fMRI_QCtoolkit.utils.filter_components_utils import (
    process_quantitative_configs,
    create_quantitative_slider,
    create_qualitative_dropdown,
    create_fraction_sliders
)


class TestProcessQuantitativeConfigs:
    
    def test_uses_provided_min_max(self, sample_afni_data):
        """Test using the min/max values provided in the configuration file."""
        configs = [{
            "variable": "cens_frac",
            "label": "Censor Fraction",
            "min_value": 0,
            "max_value_offset": 0.1,
            "default_range": [0, 0.15],
            "step": 0.01
        }]
        
        result = process_quantitative_configs(sample_afni_data, configs)
        
        var, label, min_val, max_val, default_range, step = result[0]
        assert min_val == 0
        assert max_val > 0  # data_max + offset
        assert default_range == [0, 0.15]
    
    def test_calculates_min_max_from_data(self, sample_afni_data):
        """Compute min/max"""
        configs = [{
            "variable": "TSNR",
            "label": "TSNR",
            "min_value": None, 
            "max_value_offset": None, 
            "default_range": None,
            "step": 1
        }]
        
        result = process_quantitative_configs(sample_afni_data, configs)
        
        var, label, min_val, max_val, default_range, step = result[0]
        
        # min = data_min - offset
        data_min = sample_afni_data['TSNR'].min()
        assert min_val == data_min - 1  # step >= 1, so offset = 1
        
        # max = data_max + offset
        data_max = sample_afni_data['TSNR'].max()
        assert max_val == data_max + 1
    
    def test_default_range_uses_min_max(self, sample_afni_data):
        """Default range uses min/max"""
        configs = [{
            "variable": "TSNR",
            "label": "TSNR",
            "min_value": None,
            "max_value_offset": None,
            "default_range": None,  # [min, max]
            "step": 1
        }]
        
        result = process_quantitative_configs(sample_afni_data, configs)

        var, label, min_val, max_val, default_range, step = result[0]
        
        assert default_range == [min_val, max_val]
    
    def test_step_size_affects_offset(self, sample_afni_data):
        """Test the impact of step size on offset calculation"""
        # step < 1: offset = 0.1
        configs_small_step = [{
            "variable": "cens_frac",
            "label": "Censor Fraction",
            "min_value": None,
            "max_value_offset": None,
            "default_range": None,
            "step": 0.01
        }]
        
        result = process_quantitative_configs(sample_afni_data, configs_small_step)
        _, _, min_val, max_val, _, _ = result[0]
        
        data_min = sample_afni_data['cens_frac'].min()
        data_max = sample_afni_data['cens_frac'].max()
        
        assert min_val == pytest.approx(data_min - 0.1)
        assert max_val == pytest.approx(data_max + 0.1)


class TestCreateQuantitativeSlider:
    """Test the creation of a quantifiable slider"""
    
    def test_creates_slider_component(self):
        """Test the creation of a slider component"""
        component = create_quantitative_slider(
            var="cens_frac",
            label="Censor Fraction",
            min_val=0.0,
            max_val=1.0,
            default_val=[0.0, 0.15],
            step=0.01
        )
        
        assert component is not None
        assert hasattr(component, 'children')
    
    def test_handles_nan_values(self):
        """handle NaN"""

        component = create_quantitative_slider(
            var="test_var",
            label="Test",
            min_val=np.nan,
            max_val=np.nan,
            default_val=[0.0, 1.0],
            step=0.01
        )
        
        assert component is not None


class TestCreateQualitativeDropdown:
    
    def test_creates_dropdown_component(self):
        options = [
            {'label': 'Good', 'value': 'good'},
            {'label': 'Bad', 'value': 'bad'}
        ]
        
        component = create_qualitative_dropdown(
            group="FINAL_rating",
            options=options,
            defaults=['good', 'bad']
        )
        
        assert component is not None
        assert hasattr(component, 'children')


class TestCreateFractionSliders:
    """Test fraction TRs censored"""
    
    def test_creates_fraction_sliders(self, sample_afni_data):
        df = sample_afni_data.copy()
        n = len(df)
        
        df['frac_TRs_cens_1'] = np.random.uniform(0.1, 0.2, n)
        df['frac_TRs_cens_2'] = np.random.uniform(0.12, 0.22, n)
        
        frac_defaults = {
            "range": [0, 0.2],
            "step": 0.01,
            "marks": {"0": "0", "0.2": "0.2", "1": "1"}
        }
        
        components = create_fraction_sliders(df, frac_defaults)
        
        assert len(components) == 2