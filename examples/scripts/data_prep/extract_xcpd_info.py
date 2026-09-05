# --------------------------------------------------------------------------------------
# Author: Qiuyu Yu
# Created: 2025-08-We 12:56:40
# Last Modified: Wed Aug 06 2025
# Department: Georgia Center for Developmental Science, University of Georgia
#  
# Description: After extracting the MRIQC parameters (especially spacing_tr), 
# extract num_retained_volumes from XCP-D and calculate the number of seconds for each run,
# and the total number of seconds for each subject.
# 
# Usage: `python extract_xcpd_info.py`
# --------------------------------------------------------------------------------------

import os
import pandas as pd
import glob

# base_path = "/work/cglab/projects/DORRY/reanalysis_QY/wave1/derivatives_xcpd"
# qc_csv_path = "/work/cglab/projects/DORRY/reanalysis_QY/quality_control/w1_fmriprep_rating.csv"
# output_dir = "/work/cglab/projects/DORRY/reanalysis_QY/quality_control"

base_path = "/work/cglab/projects/DORRY/reanalysis_QY/wave2/derivatives_xcpd"
qc_csv_path = "/scratch/qy49547/test/df_final.csv"
output_dir = "/scratch/qy49547/test"


results = []

# Find all tsv files
pattern = os.path.join(base_path, "sub-*", "**", "func", "sub-*task-rest_*space-fsLR_den-91k_desc-linc_qc.tsv")
tsv_files = glob.glob(pattern, recursive=True)

for tsv_path in tsv_files:
    try:
        df = pd.read_csv(tsv_path, sep='\t')
        
        # Extract sub-ID and run from files names
        filename = os.path.basename(tsv_path)
        parts = filename.split('_')
        sub = [p for p in parts if p.startswith("sub-")][0].replace("sub-", "")
        run = next((p for p in parts if p.startswith("run-")), 1)
        num_retained = df.loc[0, 'num_retained_volumes']

        results.append({
            "ID": sub,
            "run": run,
            "num_retained_volumes": num_retained
        })
    except Exception as e:
        print(f"Error processing {tsv_path}: {e}")

df = pd.DataFrame(results)
# print(df)

# ID stays a string so zero-padded labels survive and match the QC summary
df.rename(columns={"num_retained_volumes": "retained_TRs"}, inplace=True)

# Read QC summary
qc_df = pd.read_csv(qc_csv_path, dtype={'ID': str})
# print(qc_df)

# Merge two dataframes based on ID and run number
merged_df = pd.merge(qc_df, df, on=["ID", "run"], how="left")

merged_df["seconds_per_run"] = merged_df["retained_TRs"] * merged_df["spacing_tr"]

# Caculate seconds per run and total seconds for all runs per participant
total_seconds_per_ID = merged_df.groupby("ID")["seconds_per_run"].transform("sum")

merged_df["total_seconds"] = total_seconds_per_ID
# print(merged_df)

merged_df.to_csv(os.path.join(output_dir, "summary_w2.csv"), index=False)
