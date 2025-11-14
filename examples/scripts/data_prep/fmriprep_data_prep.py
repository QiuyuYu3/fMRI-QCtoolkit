# --------------------------------------------------------------------------------------
# Author: Qiuyu Yu
# Created: 2025-08-We 12:56:17
# Last Modified: Thu Oct 26 2025
# Department: Georgia Center for Developmental Science, University of Georgia
#  
# Description: Extract the rest parameters from MRIQC and the scores from fMRIprep. 
# Usage: `python fmriprep_data_prep.py`
# Change output_dir, folder, and load group_bold.tsv data.
# --------------------------------------------------------------------------------------


import pandas as pd
import glob
import os
import re
from collections import defaultdict
from pathlib import Path

# Set parameters
bold_file = '/work/cglab/projects/BRANCH/all_data/for_AFNI/BIDS/branch/quality_control/mriqc/group_bold.tsv' # MRIQC output
folder = "/scratch/qy49547/test/branch/rating" # Rating directory
output_dir = "/home/qy49547/Desktop/test"
task = 'rest'  # Specify the task to process
exclude_ids = [ ]  # IDs to exclude

# Load BOLD data and clean
bold = pd.read_csv(bold_file, sep='\t')

# Extract fields from 'bids_name'
bold['ID'] = bold['bids_name'].str.extract(r'sub-(\d+)').astype(int)
# bold['run'] = bold['bids_name'].str.extract(r'run-(\d+)').fillna(1).astype(int)
bold['run'] = bold['bids_name'].str.extract(r'run-(\d+)')[0].astype(float).fillna(1).astype(int)

# Extract the session number; if none exists, default to 1.
bold['session'] = bold['bids_name'].str.extract(r'ses-(\d+)').fillna('1').astype(int)
bold['modality'] = bold['bids_name'].str.extract(r'task-([a-zA-Z0-9]+)')

# Filter for specified task and exclude problematic IDs
if exclude_ids:
    exclude_str = " and ".join([f"ID != {id}" for id in exclude_ids])
    query_str = f"modality == '{task}' and {exclude_str}"
else:
    query_str = f"modality == '{task}'"
bold_filtered = bold.query(query_str)

# Select relevant columns
bold_clean = bold_filtered[['ID','session', 'run', 'modality', "spacing_tr",
                           'dummy_trs', 'fd_perc', 'gcor', 'gsr_x', 'gsr_y',
                           'aor', 'aqi', 'dvars_nstd', 'tsnr', 'fd_mean']]

# Load fMRIPrep QC ratings - try task-specific files first
csv_pattern = f"sub-*_{task}.csv"
csv_files = glob.glob(os.path.join(folder, csv_pattern))

# If no task-specific files found, fall back to generic files
# if not csv_files:
#     print(f"No task-specific files found, trying generic pattern...")
#     csv_files = glob.glob(os.path.join(folder, "sub-*.csv"))
#     # Filter out task-specific files to avoid duplicates
#     csv_files = [f for f in csv_files if not re.search(r'sub-\d+_\w+\.csv$', os.path.basename(f))]

print(f"Found {len(csv_files)} subject CSV files")

# Load and process each CSV, extracting session info from filename

dfs = []
for csv_file in csv_files:
    df = pd.read_csv(csv_file)
    filename = Path(csv_file).stem  # e.g., sub-267_ses-01_rest
    session_match = re.search(r'_ses-(\d+)', filename)
    if session_match:
        df['session'] = int(session_match.group(1))
    else:
        # If no session in filename, default to 1
        df['session'] = 1
    dfs.append(df)

# Concatenate all subject CSVs with session info
fmriprep_raw = pd.concat(dfs, ignore_index=True)

# Extract all *_r columns (no longer excluding Final_r)
r_cols = [col for col in fmriprep_raw.columns if col.endswith('_r')]

# Convert wide to long format per run
rows = []

for _, row in fmriprep_raw.iterrows():
    runs_data = defaultdict(dict)
    
    # Process all rating columns
    for col in r_cols:
        match = re.match(r'(\w+?)_(\d+)_r', col)
        if match:
            step, run = match.groups()
            run = int(run)
            key = (row['ID'], run)
            runs_data[key]['ID'] = row['ID']
            runs_data[key]['run'] = run
            runs_data[key]['session'] = row.get('session', 1)
            runs_data[key][step] = row[col]
    
    for run_row in runs_data.values():
        rows.append(run_row)


fmriprep_qual = pd.DataFrame(rows)

# Arrange columns
step_cols = sorted([c for c in fmriprep_qual.columns if c not in ['ID', 'run']])
fmriprep_qual = fmriprep_qual[['ID', 'run'] + step_cols]

# QC distribution and ID listing
if 'Final' in fmriprep_qual.columns:
    print("\nFinal QC distribution:")
    print(fmriprep_qual['Final'].value_counts())
    for cat in ['good', 'bad', 'other']:
        ids = fmriprep_qual.loc[fmriprep_qual['Final'] == cat, 'ID'].tolist()
        if ids:
            print(f"{cat} IDs:", ids)

# Merge with MRIQC metrics
fmriprep_rating = pd.merge(fmriprep_qual, bold_clean, on=['ID', 'session', 'run'], how='outer') # inner

# Define variable lists --------------------------------------------------------------
checkbox_groups = ["Align","BOLD","CompCor","Corr","Norm","SDC","SurfRecon","T1mask","Variance","Final"]

# data clean --------------------------------------------------------------
vars = ["fd_perc","fd_mean", "gcor", "gsr_x", "gsr_y","aor","aqi","dvars_nstd","tsnr"]

# Sort by ID
fmriprep_rating = fmriprep_rating.sort_values("ID")

# Get round number
exclude_cols = ['modality']

for col in fmriprep_rating.columns:
    if col not in checkbox_groups and col not in exclude_cols:
        fmriprep_rating[col] = pd.to_numeric(fmriprep_rating[col], errors="coerce").round(3)


# Lollipop chart data ------------------------------------------------------------------
quan_data = fmriprep_rating.drop(columns=checkbox_groups)

mean_values = quan_data[vars].mean(skipna=True)

# Standardize
scaled_data = quan_data.copy()
scaled_data[vars] = (scaled_data[vars] - mean_values) / quan_data[vars].std()

# Pivot longer
lollipop_chart_data = scaled_data.melt(id_vars=["ID"], value_vars=vars,
                                       var_name="Variable", value_name="Value")

lollipop_chart_data["mean_value"] = lollipop_chart_data["Variable"].map(mean_values.to_dict())
lollipop_chart_data["subject_variable"] = lollipop_chart_data["ID"].astype(str) + "_" + lollipop_chart_data["Variable"]

lollipop_chart_data["Value"] = lollipop_chart_data["Value"].round(3)
lollipop_chart_data["mean_value"] = lollipop_chart_data["mean_value"].round(3)
lollipop_chart_data["ID_int"] = lollipop_chart_data["ID"].astype(int)
lollipop_chart_data = lollipop_chart_data.sort_values(by=["Variable", "ID_int"])

lollipop_chart_data["row_number"] = range(1, len(lollipop_chart_data) + 1)

# Save lollipop_chart_data
lollipop_chart_data.to_csv(os.path.join(output_dir, "lollipop_chart_data.csv"), index=False)

# Save with task-specific filename
output_filename = f"fmriprep_rating_{task}.csv"
fmriprep_rating.to_csv(os.path.join(output_dir, output_filename), index=False)

print(f"\nProcessing completed! Saved {len(fmriprep_rating)} records to {output_filename}")
print(f"Subjects: {len(fmriprep_rating['ID'].unique())}, Total runs: {len(fmriprep_rating)}")