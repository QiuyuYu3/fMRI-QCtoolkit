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

def _all_numbers(values):
    """Whether every value given reads as a number; out.ss_review JSON writes numbers as text."""
    present = values.dropna().astype(str).str.strip()
    present = present[present != ""]
    return not present.empty and pd.to_numeric(present, errors="coerce").notna().all()


# AFNI writes a single value as plain text and several as a list; this one is per stimulus class even when there is one
ALWAYS_LISTS = {"fraction TRs censored"}
SESSION = re.compile(r"(?<![A-Za-z0-9])ses-([A-Za-z0-9]+)")


def _split_session(subject_id, folder):
    """(participant, session) from a subject ID like sub-01_ses-01, else from a ses-<label> folder; session None if neither."""
    match = re.fullmatch(r"(.+)_ses-([A-Za-z0-9]+)", subject_id)
    if match:
        return match.group(1), match.group(2)
    sessions = SESSION.findall(folder.as_posix())
    return subject_id, sessions[-1] if sessions else None


def _describe(key):
    participant, session = key
    return participant if session is None else f"{participant} session {session}"


class AFNIPipeline(BaseDataProcessor):
    """Data processor for AFNI pipeline with flexible file discovery."""

    LOLLIPOP_VARS = ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "GCOR", "TRs_total_raw"]

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
            "ID", "session", "runs", "TRs_total_raw", "TRs_removed", "cens_mot", 
            "cens_displace", "DF_frac", "TSNR", "cens_frac", "GCOR",
            "flip_guess"
        ]
        
    def _find_json_files(self):
        """out.ss_review.*.json under QC_* folders whose path contains the task, keyed by (subject, session)."""
        if not self.work_dir or not self.work_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.work_dir}")
        
        print(f"Searching for JSON files in {self.work_dir}/**/QC_*/extra_info/, with 'task' in path")

        json_files = {}
        duplicates = {}
        qc_dirs_found = 0

        for qc_dir in self.work_dir.rglob("QC_*"):
            if not qc_dir.is_dir():
                continue
            
            # Only the path below the input folder, so a task name in the input folder's own path matches nothing
            relative = qc_dir.relative_to(self.work_dir)
            if self.task.lower() not in relative.as_posix().lower():
                continue

            qc_dirs_found += 1

            # Extract subject ID from folder name
            qc_match = re.match(r'^QC_(.+)', qc_dir.name)
            if not qc_match:
                print("No match found, skipping")
                continue
            subject_id = qc_match.group(1)
            participant, session = _split_session(subject_id, relative.parent)

            # Check if the participant is prefix + a BIDS label (e.g. prefix001, prefixA01)
            if self.prefix and not re.fullmatch(fr"{re.escape(self.prefix)}[A-Za-z0-9]+", participant):
                print(f"Subject ID {participant} does not match prefix {self.prefix}, skipping")
                continue

            json_file = qc_dir / "extra_info" / f"out.ss_review.{subject_id}.json"
            key = (participant, session)
            if json_file.exists():
                if key in json_files:
                    duplicates.setdefault(key, [json_files[key]]).append(json_file)
                else:
                    json_files[key] = json_file
            else:
                print(f"Warning: Expected JSON file not found: {json_file}")

        print(f"Searched {qc_dirs_found} QC_* directories (with 'task'), found {len(json_files)} valid JSON files")

        # One row per participant and session: several matches would overwrite each other
        if duplicates:
            listing = "\n".join(f"  {_describe(key)}: " + ", ".join(str(path) for path in paths)
                                for key, paths in sorted(duplicates.items(), key=lambda item: _describe(item[0])))
            raise ValueError(
                f"Some participants have more than one QC directory matching task '{self.task}':\n{listing}\n"
                f"Narrow --task so it matches one folder per participant and session."
            )
        
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
        
        # Sessions in order, so the later sort by ID keeps each participant's sessions in order
        keys = sorted(json_files, key=lambda key: (key[1] is not None, key[1] or "", key[0]))
        loaded = []
        for key in keys:
            try:
                with open(json_files[key], "r") as f:
                    loaded.append((key, json.load(f)))
            except Exception as e:
                print(f"Warning: Error processing {json_files[key]}: {e}")

        if not loaded:
            raise ValueError("No valid data could be loaded from JSON files")

        # A field with several values in any file is numbered in every file, so one field never splits over two columns
        list_fields = ALWAYS_LISTS | {field for _, data in loaded for field, value in data.items() if isinstance(value, list)}
        with_sessions = any(session is not None for (_, session), _ in loaded)
        all_data = []
        for (participant, session), data in loaded:
            flat_data = {"ID": participant, **({"session": session} if with_sessions else {})}
            for key, value in data.items():
                clean_key = self._clean_key(key)
                if key in list_fields:
                    for idx, val in enumerate(value if isinstance(value, list) else [value], start=1):
                        flat_data[f"{clean_key}_{idx}"] = val
                else:
                    flat_data[clean_key] = value
            all_data.append(flat_data)

        self.df_raw = pd.DataFrame(all_data)
        print(f"Successfully loaded data for {len(loaded)}/{len(json_files)} QC directories")

        print("\nSample of loaded subjects:")
        for key, _ in loaded[:5]:
            print(f"  {_describe(key)} -> {json_files[key]}")
        if len(loaded) > 5:
            print(f"  ... and {len(loaded) - 5} more")
    
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
        
        # The named metrics, then every other numeric field so any can be added to the dashboard, then the ratings
        named = [col for col in self.core_cols + [c for c in df.columns if c.startswith("frac_TRs_cens_")]
                 if col in df.columns]
        ratings = [col for col in self.checkbox_groups if col in df.columns]
        others = [col for col in df.columns if col not in named and col not in ratings and _all_numbers(df[col])]
        df = df[named + others + ratings]
        
        # Clean ID column - remove prefix if it exists
        df["ID"] = df["ID"].str.removeprefix(self.prefix or "")
        
        self.df_final = df

    def _lollipop_vars(self):
        return [var for var in self.LOLLIPOP_VARS if var in self.df_final.columns]

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