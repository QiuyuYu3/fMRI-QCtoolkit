"""
AFNI-specific dashboard implementation
"""

from .base_app import BaseDashboard


class AFNIDashboard(BaseDashboard):
    """Dashboard for AFNI QC data."""

    PIPELINE = 'afni'
    RATING_LABELS = {
        "mot_rating": "motion",
        "radcor_rating": "correlation",
        "regr_rating": "regression",
        "va2t_rating": "anat to template",
        "ve2a_rating": "EPI to anat",
        "vorig_rating": "vorig",
        "vstat_rating": "vstat",
        "warns_rating": "warnings",
        "qsumm_rating": "quantitative",
        "FINAL_rating": "final",
    }

    def __init__(self, data_processor, *args, **kwargs):
        # One panel per session when the data has sessions; otherwise one panel for everyone
        if 'session' in data_processor.get_data().columns:
            self.GROUP_BY = 'session'
        super().__init__(data_processor, *args, **kwargs)
