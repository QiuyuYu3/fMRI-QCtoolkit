import os
import re
import json
import pandas as pd
import numpy as np

session = "01"
prefix = "sub-"
project = "branch"
task = "kidvid_output"

# Set paths
based_dir = "/work/cglab/projects/BRANCH/all_data/for_AFNI/BIDS"
output_dir = "/home/qy49547/Desktop/test"
work_dir = os.path.join(based_dir, project, "AFNI_derivatives")

# Define variable lists --------------------------------------------------------------
rating_bases = ["vorig", "ve2a", "va2t", "vstat", "mot", "regr", "radcor", "warns", "qsumm", "FINAL"]
core_cols = ["ID", "runs", "TRs_total_raw", "TRs_removed", "cens_mot", "cens_displace", "DF_frac", "TSNR", "cens_frac", "GCOR"]

# data clean --------------------------------------------------------------

# Create folder list with pattern "prefix"
if not os.path.exists(work_dir):
    raise FileNotFoundError(f"{work_dir} does not exist")

folders = [os.path.join(work_dir, f) for f in os.listdir(work_dir)
           if os.path.isdir(os.path.join(work_dir, f)) and re.match(fr"^{prefix}\d{{3}}$", f)]

all_data = []

def clean_key(key):
    key = re.sub(r"\s+", "_", key)
    key = re.sub(r"[()]", "", key)
    return key

# Extract all data from json file

for folder in folders:
    ID = os.path.basename(folder)
    json_path = os.path.join(folder, f"ses-{session}", f"{task}", f"{ID}.results",
                             f"QC_{ID}", "extra_info", f"out.ss_review.{ID}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            flat_data = {"ID": ID}

            for key, value in data.items():
                clean = clean_key(key)
                if isinstance(value, list):
                    for idx, val in enumerate(value, start=1):
                        flat_data[f"{clean}_{idx}"] = val
                else:
                    flat_data[clean] = value

            all_data.append(flat_data)
        except Exception:
            pass
        # except Exception as e:
        #     print(f"error: {e}")
    else:
        # print(f"cannot find JSON file: {json_path}")
        pass

# Convert list of dicts to DataFrame
df = pd.DataFrame(all_data)

# Recode NO_FLIP to 0
def flip_convert(val):
    if val == "NO_FLIP":
        return 0
    elif pd.notna(val):
        return 1
    return np.nan
    
df["flip_guess"] = df["flip_guess"].apply(flip_convert)

# Generate renaming dictionary
rename_dict = {
    "num_runs_found": "runs",
    "TRs_total_uncensored": "TRs_total_raw",
    "TRs_removed_per_run": "TRs_removed",
    "average_censored_motion": "cens_mot",
    "max_censored_displacement": "cens_displace",
    "final_DF_fraction": "DF_frac",
    "TSNR_average": "TSNR",
    "censor_fraction": "cens_frac",
    "global_correlation_GCOR": "GCOR",
    **{f"fraction_TRs_censored_{i}": f"frac_TRs_cens_{i}" for i in range(1, 99)},
    **{f"{col}_rating": f"{col}_r" for col in rating_bases}
}
df.rename(columns=rename_dict, inplace=True)

frac_cols = [col for col in df.columns if col.startswith("frac_TRs_cens_")]
checkbox_groups = [f"{col}_r" for col in rating_bases]
vars = ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "flip_guess", "GCOR"] + frac_cols

# Slice final DataFrame
df = df[core_cols + frac_cols + checkbox_groups]

# Process IDs and numeric columns
df["ID"] = df["ID"].str.replace(f"^{prefix}", "", regex=True)

# Sort by ID
df_final = df.sort_values("ID")

# Get round number
for col in df_final.columns:
    if col not in checkbox_groups:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").round(3)

# Lollipop chart data ------------------------------------------------------------------
quan_data = df_final.drop(columns=checkbox_groups)
vars_of_interest = ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "GCOR", "TRs_total_raw"]

mean_values = quan_data[vars_of_interest].mean(skipna=True)

# Standardize
scaled_data = quan_data.copy()
scaled_data[vars_of_interest] = (scaled_data[vars_of_interest] - mean_values) / quan_data[vars_of_interest].std()

# Pivot longer
lollipop_chart_data = scaled_data.melt(id_vars=["ID"], value_vars=vars_of_interest,
                                       var_name="Variable", value_name="Value")

lollipop_chart_data["mean_value"] = lollipop_chart_data["Variable"].map(mean_values.to_dict())
lollipop_chart_data["subject_variable"] = lollipop_chart_data["ID"].astype(str) + "_" + lollipop_chart_data["Variable"]

lollipop_chart_data["Value"] = lollipop_chart_data["Value"].round(3)
lollipop_chart_data["mean_value"] = lollipop_chart_data["mean_value"].round(3)
lollipop_chart_data["ID_int"] = lollipop_chart_data["ID"].astype(int)
lollipop_chart_data = lollipop_chart_data.sort_values(by=["Variable", "ID_int"])

lollipop_chart_data["row_number"] = range(1, len(lollipop_chart_data) + 1)

# Save merged final dataframe
df_final.to_csv(os.path.join(output_dir, "df_final.csv"), index=False)
lollipop_chart_data.to_csv(os.path.join(output_dir, "lollipop_chart_data.csv"), index=False)