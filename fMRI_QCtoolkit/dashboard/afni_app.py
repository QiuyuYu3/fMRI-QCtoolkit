"""
AFNI-specific dashboard implementation
"""

from .base_app import BaseDashboard
from ..utils.status import assign_afni_status
from ..utils.filter_components_utils import generate_filter_components

class AFNIDashboard(BaseDashboard):
    """Dashboard for AFNI QC data."""
    
    def _get_config_filename(self):
        """Return the config filename for AFNI."""
        return 'afni_config.json'
    
    def assign_status(self, value, variable_name):
        """Assign status using AFNI-specific rules."""
        return assign_afni_status(value, variable_name)
    
    def get_variable_labels(self):
        """Get AFNI-specific variable labels."""
        return (self.config["variable_labels"]["quantitative"], 
                self.config["variable_labels"]["qualitative"])
    
    def get_filter_components(self):
        """Generate AFNI-specific filter components."""
        df = self.processor.get_data()
        return generate_filter_components(df, self.processor, self.config, include_fraction_sliders=True)