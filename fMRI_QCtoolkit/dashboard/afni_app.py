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
