"""
fMRIPrep-specific dashboard implementation
"""

from .base_app import BaseDashboard
from ..utils.status import assign_fmriprep_status
from ..utils.filter_components_utils import generate_filter_components

class FMRIPrepDashboard(BaseDashboard):
    """Dashboard for fMRIPrep QC data."""
    
    def _get_config_filename(self):
        """Return the config filename for fMRIPrep."""
        return 'fmriprep_config.json'
    
    def assign_status(self, value, variable_name):
        """Assign status using fMRIPrep-specific rules."""
        return assign_fmriprep_status(value, variable_name)
    
    def get_variable_labels(self):
        """Get fMRIPrep-specific variable labels."""
        return (self.config["variable_labels"]["quantitative"], 
                self.config["variable_labels"]["qualitative"])

    def get_filter_components(self):
        """Generate fMRIPrep-specific filter components."""
        df = self.processor.get_data()
        return generate_filter_components(df, self.processor, self.config, include_fraction_sliders=False)