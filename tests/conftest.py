"""
Create random data
"""

import os
from pathlib import Path
import pytest
import json
import pandas as pd
import numpy as np

@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def examples_root(project_root: Path) -> Path:
    env_path = os.environ.get("FMRI_QCTOOLKIT_EXAMPLES_DIR")
    if env_path:
        return Path(env_path)
    return project_root / "examples" / "example_data"


@pytest.fixture(scope="session")
def fmriprep_examples(examples_root: Path) -> Path:
    return examples_root / "fmriprep"


@pytest.fixture(scope="session")
def afni_examples(examples_root: Path) -> Path:
    return examples_root / "afni"


@pytest.fixture()
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path

# AFNI
@pytest.fixture()
def sample_json_data() -> dict:
    """Generate random AFNI JSON data"""
    np.random.seed(42)
    return {
        "TRs total raw": np.random.randint(200, 400),
        "TRs censored motion": np.random.randint(5, 50),
        "censor fraction": np.random.uniform(0.05, 0.25),
        "global correlation (GCOR)": np.random.uniform(0.1, 0.3),
        "flip guess": np.random.choice(["FLIP", "NO_FLIP"]),
        "TSNR": np.random.uniform(100, 300),
        "DF_frac": np.random.uniform(0.5, 0.8),
        "cens_mot": np.random.uniform(0.05, 0.2),
        "cens_displace": np.random.uniform(3, 12),
    }


@pytest.fixture()
def mock_afni_directory(tmp_path: Path, sample_json_data: dict) -> Path:
    # Directory structure: Any path containing the `task` field has QC_sub-XXX/extra_info/out.ss_review.sub-XXX.json
    root = tmp_path / "rest_output" / "anywhere"
    for sid in ("sub-001", "sub-002"):
        info_dir = root / f"QC_{sid}" / "extra_info"
        info_dir.mkdir(parents=True)
        (info_dir / f"out.ss_review.{sid}.json").write_text(json.dumps(sample_json_data))
    return tmp_path


@pytest.fixture()
def sample_afni_data() -> pd.DataFrame:
    """Generate random AFNI DataFrame"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    
    return pd.DataFrame({
        "ID": [f"{i:03d}" for i in range(1, n_subjects + 1)],
        "runs": np.random.randint(1, 4, n_subjects),
        "TRs_total_raw": np.random.randint(200, 400, n_subjects),
        "TRs_removed": np.random.randint(5, 50, n_subjects),
        "cens_mot": np.random.uniform(0.05, 0.25, n_subjects),
        "cens_displace": np.random.uniform(3, 12, n_subjects),
        "DF_frac": np.random.uniform(0.5, 0.8, n_subjects),
        "TSNR": np.random.uniform(100, 300, n_subjects),
        "cens_frac": np.random.uniform(0.05, 0.25, n_subjects),
        "GCOR": np.random.uniform(0.1, 0.3, n_subjects),
    })

# fMRIPrep
@pytest.fixture()
def random_bold_data():
    """Generate random BOLD data for fMRIPrep testing"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    n_runs = np.random.randint(1, 4)
    
    data = []
    for i in range(n_subjects):
        subject_id = np.random.randint(100, 999)
        for run in range(1, n_runs + 1):
            data.append({
                'bids_name': f'sub-{subject_id}_ses-1_task-rest_run-{run}_bold',
                'fd_perc': np.random.uniform(5, 30),
                'gcor': np.random.uniform(0.1, 0.3),
                'dummy_trs': np.random.randint(3, 8),
                'gsr_x': np.random.uniform(0.01, 0.05),
                'gsr_y': np.random.uniform(0.01, 0.05),
                'aor': np.random.uniform(0.1, 0.4),
                'aqi': np.random.uniform(0.3, 0.8),
                'dvars_nstd': np.random.uniform(0.8, 1.5),
                'tsnr': np.random.uniform(100, 300),
                'fd_mean': np.random.uniform(0.1, 0.4),
                'spacing_tr': np.random.uniform(1.5, 3.0),
            })
    
    return pd.DataFrame(data)


@pytest.fixture()
def random_rating_data():
    """Generate random rating data for fMRIPrep testing"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    
    data = []
    for i in range(n_subjects):
        subject_id = np.random.randint(100, 999)
        rating_categories = ['Align', 'BOLD', 'CompCor', 'Corr', 'Norm', 'SDC', 'SurfRecon', 'T1mask', 'Variance', 'Final']
        ratings = np.random.choice(['good', 'bad', 'other'], len(rating_categories))
        
        row = {'ID': subject_id}
        for cat, rating in zip(rating_categories, ratings):
            row[f'{cat}_1_r'] = rating
        data.append(row)
    
    return pd.DataFrame(data)


@pytest.fixture()
def sample_fmriprep_data() -> pd.DataFrame:
    """Generate simple fMRIPrep DataFrame for basic testing"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    
    return pd.DataFrame({
        "ID": np.random.randint(100, 999, n_subjects),
        "run": np.random.randint(1, 4, n_subjects),
        "fd_perc": np.random.uniform(5, 30, n_subjects),
        "fd_mean": np.random.uniform(0.1, 0.4, n_subjects),
        "gcor": np.random.uniform(0.1, 0.3, n_subjects),
        "tsnr": np.random.uniform(100, 300, n_subjects),
        "gsr_x": np.random.uniform(0.01, 0.05, n_subjects),
        "gsr_y": np.random.uniform(0.01, 0.05, n_subjects),
        "aor": np.random.uniform(0.1, 0.4, n_subjects),
        "aqi": np.random.uniform(0.3, 0.8, n_subjects),
        "dvars_nstd": np.random.uniform(0.8, 1.5, n_subjects),
    })

# Plotting
@pytest.fixture()
def random_plot_data():
    """Generate random data for plotting tests"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    n_vars = np.random.randint(2, 5)
    
    data = []
    for i in range(n_subjects):
        subject_id = f"{i+1:03d}"
        for j in range(n_vars):
            var_name = f"var{j+1}"
            data.append({
                'ID': subject_id,
                'Variables': var_name,
                'Status': np.random.choice([1, 2, 3]),
                'StatusStr': np.random.choice(['bad', 'other', 'good']),
                'Value': np.random.uniform(0.1, 1.0),
                'run': np.random.randint(1, 3)
            })
    
    return pd.DataFrame(data)


@pytest.fixture()
def random_lollipop_data():
    """Generate random lollipop plot data"""
    np.random.seed(42)
    n_subjects = np.random.randint(3, 8)
    n_vars = np.random.randint(2, 4)
    
    data = []
    row_num = 1
    for j in range(n_vars):
        var_name = f"var{j+1}"
        mean_val = np.random.uniform(0.1, 0.5)
        
        for i in range(n_subjects):
            subject_id = f"{i+1:03d}"
            data.append({
                'ID': subject_id,
                'Variable': var_name,
                'Value': np.random.uniform(0.05, 0.8),
                'mean_value': mean_val,
                'row_number': row_num
            })
            row_num += 1
    
    return pd.DataFrame(data)


