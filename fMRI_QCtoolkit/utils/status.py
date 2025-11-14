"""
Status assignment utilities for quality control metrics
"""

import pandas as pd

def assign_afni_status(value, variable_name):
    """
    Assign status for AFNI pipeline variables.
    """
    if pd.isna(value):
        return "NA"
    
    variable_name = str(variable_name)
    
    if variable_name == "DF_frac":
        if value > 0.7:
            return "good"
        elif value > 0.6:
            return "other"
        else:
            return "bad"
    elif variable_name == "cens_frac":
        if value >= 0.2:
            return "bad"
        elif value >= 0.15:
            return "other"
        else:
            return "good"
    elif variable_name == "cens_mot":
        if value >= 0.15:
            return "bad"
        elif value >= 0.1:
            return "other"
        else:
            return "good"
    elif variable_name == "cens_displace":
        if value >= 8:
            return "bad"
        elif value >= 6:
            return "other"
        else:
            return "good"
    elif variable_name == "GCOR":
        if value >= 0.2:
            return "bad"
        elif value >= 0.15:
            return "other"
        else:
            return "good"
    elif variable_name == "flip_guess":
        if value == 0:
            return "good"
        else:
            return "bad"
    elif variable_name == "TSNR":
        if value <= 150:
            return "other"
        else:
            return "good"
    else:
        return "other"


def assign_fmriprep_status(value, variable_name):
    """
    Assign status for fMRIPrep pipeline variables.
    """
    if pd.isna(value):
        return "NA"
    
    variable_name = str(variable_name)
    
    if variable_name == "fd_perc":
        if value > 20:
            return "bad"
        elif value > 15:
            return "other"
        else:
            return "good"
    elif variable_name == "fd_mean":
        if value >= 0.3:
            return "bad"
        elif value >= 0.2:
            return "other"
        else:
            return "good"
    elif variable_name == "gcor":
        if value >= 0.2:
            return "bad"
        elif value > 0.15:
            return "other"
        else:
            return "good"
    elif variable_name == "tsnr":
        if value <= 150:
            return "other"
        else:
            return "good"
    else:
        return "other"


def get_status_mapping():
    """
    Get numerical mapping for status values.
    """
    return {'NA': 0, 'bad': 1, 'other': 2, 'good': 3}


def get_status_colors():
    """
    Get color mapping for status values.
    """
    return {
        0: '#D3D3D3',  # NA - light gray
        1: '#F8786E',  # bad - red
        2: '#FFD966',  # other - yellow
        3: '#C5E0B3'   # good - green
    }