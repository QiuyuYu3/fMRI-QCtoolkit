"""
Base data processor for MRI QC pipelines
"""

import pandas as pd
from pathlib import Path
from abc import ABC, abstractmethod

class BaseDataProcessor(ABC):
    """Base class for data processors."""
    
    def __init__(self, task="", output_dir=""):
        self.task = task
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Data containers
        self.df_final = None
        self.lollipop_chart_data = None
        self.vars = []
        self.checkbox_groups = []
    
    @abstractmethod
    def _set_variables(self):
        """Set pipeline-specific variables and checkbox groups."""
        pass
    
    @abstractmethod
    def _load_raw_data(self):
        """Load raw data from source."""
        pass
    
    @abstractmethod
    def _clean_data(self):
        """Clean and process raw data."""
        pass
    
    def _prepare_lollipop_data(self, vars_of_interest):
        """Prepare standardized data for lollipop chart."""
        # Create a copy of df_final excluding checkbox groups for quantitative analysis
        quan_data = self.df_final.drop(columns=self.checkbox_groups, errors='ignore')
        
        # Ensure all variables are numeric
        for var in vars_of_interest:
            if var in quan_data.columns:
                quan_data[var] = pd.to_numeric(quan_data[var], errors='coerce')
        
        # Calculate mean and standard deviation for scaling
        mean_values = quan_data[vars_of_interest].mean(skipna=True)
        std_values = quan_data[vars_of_interest].std(skipna=True)
        
        # Create scaled data (z-scores)
        scaled_data = quan_data.copy()
        for var in vars_of_interest:
            if var in scaled_data.columns and std_values[var] != 0:
                scaled_data[var] = (scaled_data[var] - mean_values[var]) / std_values[var]
        
        # Pivot to long format for visualization (keep session/run for grouping)
        id_vars = ["ID"] + [c for c in ("session", "run") if c in scaled_data.columns]
        lollipop_data = scaled_data.melt(
            id_vars=id_vars,
            value_vars=vars_of_interest,
            var_name="Variable",
            value_name="Value"
        )
        
        # Add metadata
        lollipop_data["mean_value"] = lollipop_data["Variable"].map(mean_values.to_dict())
        lollipop_data["subject_variable"] = (
            lollipop_data["ID"].astype(str) + "_" + lollipop_data["Variable"]
        )
        
        # Round values for display
        lollipop_data["Value"] = lollipop_data["Value"].round(3)
        lollipop_data["mean_value"] = lollipop_data["mean_value"].round(3)
        
        # Sort and add row numbers
        lollipop_data["ID_int"] = pd.to_numeric(lollipop_data["ID"], errors='coerce')
        lollipop_data = lollipop_data.sort_values(by=["Variable", "ID_int"])
        lollipop_data["row_number"] = range(1, len(lollipop_data) + 1)
        
        # Remove temporary ID_int column
        lollipop_data = lollipop_data.drop('ID_int', axis=1)
        
        self.lollipop_chart_data = lollipop_data

    def _round_numeric_columns(self):
        """Round numeric columns to 3 decimal places."""
        for col in self.df_final.columns:
            if col not in self.checkbox_groups:
                if pd.api.types.is_numeric_dtype(self.df_final[col]):
                    self.df_final[col] = self.df_final[col].round(3)

    def _sort_by_id(self):
        """Sort by ID numerically where possible, so sub-9 precedes sub-10."""
        if 'ID' in self.df_final.columns:
            order = pd.to_numeric(self.df_final["ID"], errors="coerce")
            self.df_final = (self.df_final
                             .assign(_id_num=order)
                             .sort_values(["_id_num", "ID"], na_position="last")
                             .drop(columns="_id_num"))
    
    def save_data(self):
        """Save processed data to CSV files."""
        if self.df_final is not None:
            df_path = self.output_dir / "df_final.csv"
            self.df_final.to_csv(df_path, index=False)
            print(f"Saved final dataframe to: {df_path}")
        
        if self.lollipop_chart_data is not None:
            lollipop_path = self.output_dir / "lollipop_chart_data.csv"
            self.lollipop_chart_data.to_csv(lollipop_path, index=False)
            print(f"Saved lollipop data to: {lollipop_path}")
    
    def process(self):
        """Main processing pipeline."""
        print("Loading raw data...")
        self._load_raw_data()
        
        print("Cleaning data...")
        self._clean_data()
        
        print("Processing final dataframe...")
        self._round_numeric_columns()
        self._sort_by_id()
        
        # Save processed data
        self.save_data()
        
        print("Data processing complete!")
        
        return self
    
    def get_summary(self):
        """Get summary statistics of processed data."""
        if self.df_final is None:
            return "No data processed yet."
        
        summary = {
            "task": self.task,
            "n_records": len(self.df_final),
            "n_subjects": len(self.df_final['ID'].unique()) if 'ID' in self.df_final.columns else 0,
            "n_variables": len(self.df_final.columns),
            "quantitative_vars": len(self.vars),
            "qualitative_vars": len(self.checkbox_groups),
            "missing_data": self.df_final.isnull().sum().sum()
        }
        
        if 'run' in self.df_final.columns:
            summary["n_runs"] = len(self.df_final['run'].unique())
            summary["runs_per_subject"] = self.df_final.groupby('ID')['run'].count().mean() if 'ID' in self.df_final.columns else 0
        
        return summary