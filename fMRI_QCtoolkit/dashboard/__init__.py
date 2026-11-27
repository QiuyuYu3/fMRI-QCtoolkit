"""
Dashboard modules for MRI QC visualization
"""

from .base_app import BaseDashboard
from .afni_app import AFNIDashboard
from .custom_app import CustomDashboard
from .fmriprep_app import FMRIPrepDashboard

__all__ = [
    'BaseDashboard',
    'AFNIDashboard',
    'CustomDashboard',
    'FMRIPrepDashboard'
]