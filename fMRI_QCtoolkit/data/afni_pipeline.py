"""
AFNI-specific data processor with flexible file search
"""

import pandas as pd
import numpy as np
import json
import os
import re
from pathlib import Path
from .base import BaseDataProcessor

class AFNIPipeline(BaseDataProcessor):
    """Data processor for AFNI pipeline with flexible file discovery."""
    
    def __init__(self, input_dir, task, prefix, output_dir):
        super().__init__(task, output_dir)
        self.input_dir = Path(input_dir)
        self.prefix = prefix
        self.work_dir = self.input_dir
        self.task = task
    
    def _set_variables(self):
        """Set AFNI-specific variables."""
        self.checkbox_groups = [
            "vorig_rating", "ve2a_rating", "va2t_rating", "vstat_rating", 
            "mot_rating", "regr_rating", "radcor_rating", "warns_rating", 
            "qsumm_rating", "FINAL_rating"
        ]
        
        # Get frac columns from dataframe if available
        if self.df_final is not None:
            frac_cols = [col for col in self.df_final.columns if col.startswith("frac_TRs_cens_")]
        else:
            frac_cols = []
        
        self.vars = [
            "cens_frac", "cens_mot", "cens_displace", "TSNR", 
            "DF_frac", "flip_guess", "GCOR"
        ] + frac_cols
        
        self.core_cols = [
            "ID", "runs", "TRs_total_raw", "TRs_removed", "cens_mot", 
            "cens_displace", "DF_frac", "TSNR", "cens_frac", "GCOR",
            "flip_guess"
        ]
        
    def _find_json_files(self):
        """
        Find all out.ss_review.*.json files under */QC_*/extra_info/ 
        where the path contains the specified task. Could be ses-01/{task}_output
        Subject ID still must match the prefix pattern.
        """
        if not self.work_dir or not self.work_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.work_dir}")
        
        print(f"Searching for JSON files in {self.work_dir}/**/QC_*/extra_info/, with 'task' in path")

        json_files = {}
        qc_dirs_found = 0

        for qc_dir in self.work_dir.rglob("QC_*"):
            if not qc_dir.is_dir():
                continue
            
            # Filter by task string in the full path (case-insensitive optional)
            if self.task.lower() not in qc_dir.as_posix().lower():
                continue

            qc_dirs_found += 1

            # Extract subject ID from folder name
            qc_match = re.match(r'^QC_(.+)', qc_dir.name)
            if not qc_match:
                print("No match found, skipping")
                continue
            subject_id = qc_match.group(1)

            # Check if subject_id matches prefix + digits (e.g. prefix001)
            if self.prefix and not re.match(fr"^{self.prefix}\d+$", subject_id):
                print(f"Subject ID {subject_id} does not match prefix {self.prefix}, skipping")
                continue

            json_file = qc_dir / "extra_info" / f"out.ss_review.{subject_id}.json"
            if json_file.exists():
                json_files[subject_id] = json_file
            else:
                print(f"Warning: Expected JSON file not found: {json_file}")

        print(f"Searched {qc_dirs_found} QC_* directories (with 'task'), found {len(json_files)} valid JSON files")
        
        return json_files

    def _load_raw_data(self):
        """Load AFNI data from JSON files with flexible search."""
        # Find all relevant JSON files
        json_files = self._find_json_files()
        
        if not json_files:
            raise FileNotFoundError(
                f"No out.ss_review.*.json files found in {self.work_dir}. "
                f"Please check that the directory contains AFNI QC output files."
            )
        
        print(f"Found {len(json_files)} JSON files to process")
        
        all_data = []
        successful_loads = 0
        
        for subject_id, json_path in json_files.items():
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                
                flat_data = {"ID": subject_id}
                
                # Flatten nested data
                for key, value in data.items():
                    clean_key = self._clean_key(key)
                    if isinstance(value, list):
                        for idx, val in enumerate(value, start=1):
                            flat_data[f"{clean_key}_{idx}"] = val
                    else:
                        flat_data[clean_key] = value
                
                all_data.append(flat_data)
                successful_loads += 1
                
            except Exception as e:
                print(f"Warning: Error processing {json_path}: {e}")
                continue
        
        if not all_data:
            raise ValueError("No valid data could be loaded from JSON files")
        
        self.df_raw = pd.DataFrame(all_data)
        print(f"Successfully loaded data for {successful_loads}/{len(json_files)} subjects")
        
        # Show sample of found files for verification
        if successful_loads > 0:
            print("\nSample of loaded subjects:")
            sample_size = min(5, len(all_data))
            for i, row in enumerate(self.df_raw.head(sample_size).itertuples()):
                corresponding_file = json_files.get(row.ID, "Unknown")
                print(f"  {row.ID} -> {corresponding_file}")
            if len(all_data) > sample_size:
                print(f"  ... and {len(all_data) - sample_size} more")
    
    def _clean_key(self, key):
        """Clean JSON keys for column names."""
        key = re.sub(r"\s+", "_", key)
        key = re.sub(r"[()]", "", key)
        return key
    
    def _clean_data(self):
        """Clean and process AFNI data."""
        df = self.df_raw.copy()
        
        # Convert flip_guess values
        def flip_convert(val):
            if val == "NO_FLIP":
                return 0
            elif pd.notna(val):
                return 1
            return np.nan
        
        if "flip_guess" in df.columns:
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
        }
        
        # Add fraction columns mapping
        for i in range(1, 99):
            rename_dict[f"fraction_TRs_censored_{i}"] = f"frac_TRs_cens_{i}"
        
        # Add checkbox groups mapping
        for col in self.checkbox_groups:
            rename_dict[col] = col
        
        df = df.rename(columns=rename_dict)
        
        # Set variables based on available columns
        self._set_variables()
        
        # Select final columns
        available_cols = [
            col for col in (
                self.core_cols + 
                [col for col in df.columns if col.startswith("frac_TRs_cens_")] + 
                self.checkbox_groups
            ) 
            if col in df.columns
        ]
        df = df[available_cols]
        
        # Clean ID column - remove prefix if it exists
        df["ID"] = df["ID"].str.replace(f"^{self.prefix}", "", regex=True)
        
        self.df_final = df
        
        # Prepare lollipop data
        vars_of_interest = [
            "cens_frac", "cens_mot", "cens_displace", "TSNR", 
            "DF_frac", "GCOR", "TRs_total_raw"
        ]
        # Filter to only available variables
        vars_of_interest = [var for var in vars_of_interest if var in self.df_final.columns]
        
        self._prepare_lollipop_data(vars_of_interest)
    
    def get_search_summary(self):
        """Get summary of file search results for debugging."""
        if not hasattr(self, 'df_final') or self.df_final is None:
            return "No data processed yet."
        
        json_files = self._find_json_files()
        
        summary = {
            "search_directory": str(self.work_dir),
            "json_files_found": len(json_files),
            "subjects_processed": len(self.df_final),
            "search_pattern": f"out.ss_review.*.json (with prefix '{self.prefix}')",
            "sample_files": list(json_files.items())[:3]  # Show first 3 as example
        }
        
        return summary
    
    @classmethod
    def from_saved_data(cls, data_file, lollipop_file, task=None, output_dir=None):
        """Create instances from saved CSV files (for dashboard)"""
        instance = cls.__new__(cls)
        
        instance.task = task or ""
        instance.output_dir = Path(output_dir) if output_dir else Path(".")
        
        # load csv files
        instance.df_final = pd.read_csv(data_file, dtype={'ID': str})
        instance.lollipop_chart_data = pd.read_csv(lollipop_file, dtype={'ID': str})
        
        instance._set_variables()
        
        return instance
    
    def get_data(self):
        return self.df_final
    
    def get_lollipop_data(self):
        return self.lollipop_chart_data