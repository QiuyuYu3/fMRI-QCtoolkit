import numpy as np
import pandas as pd
from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent / "random_data"
EXAMPLES_ROOT.mkdir(exist_ok=True) 

def generate_subject_ids(n_subjects=5):
    """Generate standardized subject IDs like '001', '002', ..."""
    return [f"{i+1:03d}" for i in range(n_subjects)]

def add_random_nans(df, missing_rate=0.05):
    """Randomly set some values in the DataFrame to NaN, excluding the first column (ID)."""
    df = df.copy()
    n_rows, n_cols = df.shape
    n_missing = int(n_rows * n_cols * missing_rate)
    
    for _ in range(n_missing):
        i = np.random.randint(0, n_rows)
        j = np.random.randint(1, n_cols)  # avoid ID column
        df.iat[i, j] = np.nan
    return df

def generate_afni_data(subject_ids, seed=42, missing_rate=0.05, save=True, filename="afni_quan_data.csv"):
    """Generate random AFNI quantitative QC table with optional missing values."""
    np.random.seed(seed)
    n_subjects = len(subject_ids)

    df = pd.DataFrame({
        "ID": subject_ids,
        "runs": np.random.randint(1, 4, n_subjects),
        "TRs_total_raw": np.random.randint(200, 400, n_subjects),
        "TRs_removed": np.random.randint(5, 50, n_subjects),
        "cens_mot": np.random.uniform(0.05, 0.25, n_subjects),
        "cens_displace": np.random.uniform(3, 12, n_subjects),
        "DF_frac": np.random.uniform(0.5, 0.8, n_subjects),
        "TSNR": np.random.uniform(100, 300, n_subjects),
        "cens_frac": np.random.uniform(0.05, 0.25, n_subjects),
        "frac_TRs_cens_1": np.random.uniform(0.1, 0.5, n_subjects),
        "frac_TRs_cens_2": np.random.uniform(0.1, 0.5, n_subjects),
        "GCOR": np.random.uniform(0.1, 0.3, n_subjects),
    })

    df = add_random_nans(df, missing_rate)

    if save:
        df.to_csv(EXAMPLES_ROOT / filename, index=False)
    return df


def generate_fmriprep_bold_data(subject_ids, seed=42, missing_rate=0.05, save=True, filename="fmriprep_quan_data.csv"): 
    """Generate random fMRIPrep BOLD quantitative QC table with optional missing values."""
    np.random.seed(seed)
    n_runs = np.random.randint(1, 4)

    data = []
    for subject_id in subject_ids:
        for run in range(1, n_runs + 1):
            row = {
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
            }
            # Randomly set some values to NaN
            for key in list(row.keys())[1:]:  # exclude bids_name
                if np.random.rand() < missing_rate:
                    row[key] = np.nan
            data.append(row)

    df = pd.DataFrame(data)
    if save:
        df.to_csv(EXAMPLES_ROOT / filename, index=False)
    return df


def generate_fmriprep_rating_data_per_subject(subject_ids, seed=42, max_repeat=3, missing_rate=0.05):
    """Generate random fMRIPrep rating CSV files per subject/session with optional missing values."""
    np.random.seed(seed)
    rating_categories_fixed1 = ['T1mask', 'Norm', 'SurfRecon']
    rating_categories_seq = ['SDC', 'Align', 'CompCor', 'Variance', 'BOLD', 'Corr', 'Final']
    tasks = ['nback', 'rest']

    output_dir = EXAMPLES_ROOT / "fmriprep_rating"
    output_dir.mkdir(exist_ok=True)

    for subject_id in subject_ids:
        n_sessions = np.random.randint(1, 4)
        cat_counters = {cat: 1 for cat in rating_categories_seq}

        for ses_idx in range(n_sessions):
            ses_str = f"ses-{ses_idx+1:02d}"
            task = tasks[ses_idx % len(tasks)]
            row = {'ID': subject_id}

            # Fixed columns with _1
            for cat in rating_categories_fixed1:
                row[f"{cat}_1_r"] = np.random.choice(['good','bad','other'])
                row[f"{cat}_1_c"] = np.random.choice(['good','bad','other'])

            # Random number of columns for other categories
            for cat in rating_categories_seq:
                n_cols = np.random.randint(1, max_repeat + 1)
                for idx in range(cat_counters[cat], cat_counters[cat] + n_cols):
                    val_r = np.random.choice(['good','bad','other'])
                    val_c = np.random.choice(['good','bad','other'])
                    
                    # Apply missing values with given probability
                    if np.random.rand() < missing_rate:
                        val_r = np.nan
                    if np.random.rand() < missing_rate:
                        val_c = np.nan
                    row[f"{cat}_{idx}_r"] = val_r
                    row[f"{cat}_{idx}_c"] = val_c
                cat_counters[cat] += n_cols

            df = pd.DataFrame([row])
            filename = f"sub-{subject_id}_{ses_str}_{task}.csv"
            df.to_csv(output_dir / filename, index=False)


def generate_fmriprep_summary(subject_ids, seed=42, missing_rate=0.05, save=True, filename="fmriprep_selected_quan_data.csv"):
    """Generate selected quantitative fMRIPrep QC table with optional missing values."""
    np.random.seed(seed)
    n_subjects = len(subject_ids)

    df = pd.DataFrame({
        "ID": subject_ids,
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

    df = add_random_nans(df, missing_rate)

    if save:
        df.to_csv(EXAMPLES_ROOT / filename, index=False)
    return df


if __name__ == "__main__":
    n_subjects = 5
    subject_ids = generate_subject_ids(n_subjects)

    generate_afni_data(subject_ids, missing_rate=0.1)
    generate_fmriprep_bold_data(subject_ids, missing_rate=0.1)
    generate_fmriprep_rating_data_per_subject(subject_ids, missing_rate=0.1)
    generate_fmriprep_summary(subject_ids, missing_rate=0.1)
