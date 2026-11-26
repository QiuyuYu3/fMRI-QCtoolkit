"""
Process data in fMRIPrep Pipeline.
Input argument: task, bold_file (group_bold.tsv), rating_dir, and output_dir.

ID, session, run, and task are extracted from the 'bids_name' column in group_bold.tsv.
`COMMON_MODULES` are modules that are rated once per session instead of per run. Same in the frontend.
"""

import pandas as pd
import glob
import re
from pathlib import Path
from collections import defaultdict
from .base import BaseDataProcessor

# sub-<ID>[_ses-<session>]_<task>[_<entity>-<value>...].csv, as the rating page writes them
RATING_FILE = re.compile(r'sub-[A-Za-z0-9]+(?:_ses-[A-Za-z0-9]+)?_([A-Za-z0-9]+)(?:_[a-z]+-[A-Za-z0-9]+)*\.csv$')

class FMRIPrepPipeline(BaseDataProcessor):
    """Data processor for fMRIPrep pipeline."""
    
    def __init__(self, bold_file, rating_dir, task, output_dir):
        super().__init__(task, output_dir)
        self.bold_file = Path(bold_file)
        self.rating_dir = Path(rating_dir) 
        self.task = task
        
        # Data containers
        self.bold_data = None
        self.rating_data = None
        self._set_variables()

    
    def _set_variables(self):
        """Set fMRIPrep-specific variables."""
        self.checkbox_groups = [
            "Align", "BOLD", "CompCor", "Corr", "Norm", "SDC", 
            "SurfRecon", "T1mask", "Variance", "Final"
        ]

        self.COMMON_MODULES = ["T1mask", "Norm", "SurfRecon"]

        self.vars = [
            "fd_perc", "fd_mean", "gcor", "gsr_x", "gsr_y", "aor", 
            "aqi", "dvars_nstd", "tsnr"
        ]
    
    def _load_bold_data(self):
        """Load and process BOLD data from group_bold.tsv file."""
        if not self.bold_file.exists():
            raise FileNotFoundError(f"BOLD file not found: {self.bold_file}")
        
        print(f"Loading BOLD data from: {self.bold_file}")
        
        # Load BOLD data
        bold = pd.read_csv(self.bold_file, sep='\t')
        
        # Extract fields from 'bids_name'
        bold['ID'] = bold['bids_name'].str.extract(r'sub-([A-Za-z0-9]+)')[0]
        bold['run'] = bold['bids_name'].str.extract(r'run-(\d+)')[0].astype(float).fillna(1).astype(int)
        bold['session'] = bold['bids_name'].str.extract(r'ses-([A-Za-z0-9]+)')[0].fillna('1')
        bold['task'] = bold['bids_name'].str.extract(r'task-([a-zA-Z0-9]+)')[0]

        # Filter for specified task
        bold_filtered = bold[bold['task'] == self.task]

        # Every numeric IQM, so any of them can be added to the dashboard without preparing the data again
        labels = ['ID', 'session', 'run', 'task']
        iqms = [c for c in bold.columns if c not in labels and pd.api.types.is_numeric_dtype(bold[c])]
        bold_clean = bold_filtered[labels + iqms]
        
        self.bold_data = bold_clean
        print(f"Loaded BOLD data for {len(bold_clean)} records")
        
    def _load_rating_data(self):
        """Load and process rating data from session-task-specific subject CSV files."""
        if not self.rating_dir.exists():
            raise FileNotFoundError(f"Rating directory not found: {self.rating_dir}")
        
        print(f"Loading rating data from: {self.rating_dir}")
        
        # Find session-task-specific CSV files: sub-{ID}_ses-{session}_{task}.csv
        csv_pattern = f"sub-*_{self.task}.csv"
        csv_files = glob.glob(str(self.rating_dir / csv_pattern))

        # The rating app writes one CSV per acquisition/direction/echo when a task has
        # several. The dashboard has no such dimension, so they are reported and skipped.
        split_files = glob.glob(str(self.rating_dir / f"sub-*_{self.task}_*-*.csv"))
        if split_files:
            print(f"WARNING: skipping {len(split_files)} rating file(s) split by an entity "
                  f"the dashboard cannot represent, e.g. {Path(split_files[0]).name}")

        # Never fall back to other files: they would be another task's ratings, matched on the same runs
        if not csv_files:
            raise FileNotFoundError(self._no_ratings_message())
        
        print(f"Found {len(csv_files)} subject CSV files")
        
        # Concatenate all subject CSVs
        all_ratings = []
        
        for csv_file in csv_files:
            df = pd.read_csv(csv_file, dtype={'ID': str})
            
            # Extract session from filename
            filename = Path(csv_file).stem
            session_match = re.search(r'_ses-([A-Za-z0-9]+)', filename)

            if session_match:
                df['session'] = session_match.group(1)
            else:
                # If no session in filename, default to 1
                df['session'] = '1'

            all_ratings.append(df)
        
        fmriprep_raw = pd.concat(all_ratings, ignore_index=True)
        
        # Extract all rating columns (*_r) 
        r_cols = [col for col in fmriprep_raw.columns if col.endswith('_r')]
        
        # Convert wide to long format per run
        rows = []
        
        for _, row in fmriprep_raw.iterrows():
            runs_data = defaultdict(dict)
            common_module_values = {}
            
            # Get common modules
            for col in r_cols:
                match = re.match(r'(\w+?)_(\d+)_r', col)
                if match:
                    step, run = match.groups()
                    value = row[col]
                    
                    if pd.notna(value) and step in self.COMMON_MODULES:
                        common_module_values[step] = value
            
            # Get per-run modules, drop NaNs
            for col in r_cols:
                match = re.match(r'(\w+?)_(\d+)_r', col)
                if match:
                    step, run = match.groups()
                    run = int(run)
                    value = row[col]
                    
                    if pd.notna(value):
                        key = (row['ID'], row['session'], run)
                        runs_data[key]['ID'] = row['ID']
                        runs_data[key]['session'] = row['session']
                        runs_data[key]['run'] = run
                        runs_data[key][step] = value
            
            # Fill in common module values for each run
            for key in runs_data.keys():
                for common_mod, common_val in common_module_values.items():
                    if common_mod not in runs_data[key]:
                        runs_data[key][common_mod] = common_val
            
            # Convert runs_data to list of rows
            for run_row in runs_data.values():
                rows.append(run_row)
        
        if not rows:
            raise ValueError("No valid rating data found after processing CSV files")
        
        fmriprep_qual = pd.DataFrame(rows)
        
        # Arrange columns (ID, session, run, then all rating columns alphabetically)
        step_cols = sorted([c for c in fmriprep_qual.columns if c not in ['ID', 'session', 'run']])
        fmriprep_qual = fmriprep_qual[['ID', 'session', 'run'] + step_cols]
        
        self.rating_data = fmriprep_qual
        print(f"Processed rating data for {len(fmriprep_qual)} records")
        
        # Print QC distribution for Final column if it exists
        if 'Final' in fmriprep_qual.columns:
            print("\nFinal QC distribution:")
            print(self.rating_data['Final'].value_counts())
            
            for cat in ['good', 'bad', 'other']:
                ids = self.rating_data.loc[self.rating_data['Final'] == cat, 'ID'].tolist()
                if ids:
                    print(f"{cat} IDs: {ids}")
        else:
            print("No 'Final' column found in rating data")
    
    def _no_ratings_message(self):
        tasks = sorted({m.group(1) for f in self.rating_dir.glob("sub-*.csv") if (m := RATING_FILE.match(f.name))})
        found = f"; it has ratings for: {', '.join(tasks)}" if tasks else ""
        return f"No rating files for task {self.task} in {self.rating_dir}{found}"

    def _load_raw_data(self):
        """Load both BOLD and rating data."""
        self._load_bold_data()
        self._load_rating_data()
    
    def _clean_data(self):
        """Clean and merge fMRIPrep data."""
        print("\nCleaning and merging data...")

        # Check if session column exists in both dataframes
        merge_keys = ['ID', 'run']
        if 'session' in self.rating_data.columns and 'session' in self.bold_data.columns:
            merge_keys = ['ID', 'session', 'run']
            print(f"Merging on: {merge_keys}")
        else:
            print(f"Warning: Session column not found in both datasets, merging on ID and run only")
        
        # Merge BOLD data with rating data
        merged_data = pd.merge(
            self.rating_data,
            self.bold_data,
            on=merge_keys,
            how='outer', # 'inner' join to keep only matching records. 'outer' to keep all.
            indicator=True
        )

        matched = int((merged_data['_merge'] == 'both').sum())
        merged_data = merged_data.drop(columns='_merge')

        print(f"After merge: {merged_data.shape} ({matched} matched on {merge_keys})")

        # An outer join lays both sides side by side when nothing matches, so the row
        # count can never reveal a key mismatch -- only the matched count can.
        if matched == 0:
            print(f"WARNING: no record matched on {merge_keys}! "
                  "Ratings and MRIQC are probably labelled differently.")
            for key in merge_keys:
                print(f"  {key}: rating={sorted(self.rating_data[key].unique())[:8]} "
                      f"vs BOLD={sorted(self.bold_data[key].unique())[:8]}")

        self.df_final = merged_data
        print(f"Final merged dataset: {len(merged_data)} records")

        print("\nFinal data summary:")
        print(self.df_final.head())
        print(f"\nColumns: {self.df_final.columns.tolist()}")

    def get_data_summary(self):
        """Get summary of loaded data."""
        summary = {
            "bold_file": str(self.bold_file),
            "rating_dir": str(self.rating_dir),
            "task": self.task,
            "bold_records": len(self.bold_data) if self.bold_data is not None else 0,
            "rating_records": len(self.rating_data) if self.rating_data is not None else 0,
            "final_records": len(self.df_final) if self.df_final is not None else 0
        }
        return summary