"""
fMRIPrep-specific dashboard implementation
"""

from .base_app import BaseDashboard


class FMRIPrepDashboard(BaseDashboard):
    """Dashboard for fMRIPrep QC data."""

    PIPELINE = 'fmriprep'
    GROUP_BY = ['session', 'run']
    RATING_LABELS = {
        "Align": "Coregistration",
        "BOLD": "BOLD Summary",
        "CompCor": "CompCor",
        "Corr": "Correlations",
        "Norm": "Normalization",
        "SDC": "SDC",
        "SurfRecon": "Surface Recon",
        "T1mask": "Mask & Segment",
        "Variance": "Variance",
        "Final": "Final",
    }
