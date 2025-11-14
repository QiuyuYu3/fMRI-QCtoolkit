"""
Dashboard modules for MRI QC visualization
"""

from .base_app import BaseDashboard
from .afni_app import AFNIDashboard
from .fmriprep_app import FMRIPrepDashboard

__all__ = [
    'BaseDashboard',
    'AFNIDashboard', 
    'FMRIPrepDashboard'
]