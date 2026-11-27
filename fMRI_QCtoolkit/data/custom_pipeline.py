"""Data processor for a lab's own tables of ratings and metrics, keyed by ID and optionally session and run."""

import numpy as np
import pandas as pd
from pathlib import Path
from .base import BaseDataProcessor, read_csv_exact

KEYS = ("ID", "session", "run")
RATINGS = ("good", "other", "bad")
# Removed as fmriqc prep fmriprep removes them, so sub-001 matches 001 and run-01 matches 1
PREFIXES = {"ID": "sub-", "session": "ses-", "run": "run-"}
SHOWN = 3


def _present(values):
    """The non-empty cells, as stripped text."""
    text = values.dropna().astype(str).str.strip()
    return text[text != ""]


def _all_numbers(present):
    return pd.to_numeric(present, errors="coerce").notna().all()


def classify_columns(df):
    """(ratings, metrics, table_only): non-empty cells all good/other/bad, all numbers, or anything else."""
    ratings, metrics, table_only = [], [], []
    for column in df.columns:
        if column in KEYS:
            continue
        values = df[column]
        present = _present(values)
        if present.empty or pd.api.types.is_bool_dtype(values):
            table_only.append(column)
        elif pd.api.types.is_numeric_dtype(values) or _all_numbers(present):
            metrics.append(column)
        elif present.str.lower().isin(RATINGS).all():
            ratings.append(column)
        else:
            table_only.append(column)
    return ratings, metrics, table_only


def normalize_columns(df, ratings, metrics):
    """Ratings in lower case without spaces, metrics as numbers; an empty cell becomes missing."""
    df = df.copy()
    for column in ratings:
        df[column] = df[column].map(lambda v: (v.strip().lower() or np.nan) if isinstance(v, str) else np.nan)
    for column in metrics:
        if not pd.api.types.is_numeric_dtype(df[column]):
            df[column] = pd.to_numeric(df[column].map(lambda v: (v.strip() or None) if isinstance(v, str) else v))
    return df


def odd_values(values):
    """'pass (10 rows), fail (5 rows)': the values of a table-only column that are neither ratings nor numbers."""
    present = _present(values)
    if present.empty:
        return "empty"
    odd = present[~present.str.lower().isin(RATINGS) & pd.to_numeric(present, errors="coerce").isna()]
    if odd.empty:
        return "mixes numbers with good, other or bad"
    counts = odd.value_counts()
    shown = [f"{value} ({n} row{'s' if n != 1 else ''})" for value, n in counts.head(SHOWN).items()]
    more = f" and {len(counts) - SHOWN} more" if len(counts) > SHOWN else ""
    return ", ".join(shown) + more


def _describe_key(row, keys):
    return ", ".join(f"{key} {'(empty)' if pd.isna(row[key]) else row[key]}" for key in keys)


class CustomPipeline(BaseDataProcessor):
    """Data processor for tables a lab makes itself."""

    def __init__(self, inputs, output_dir):
        super().__init__("", output_dir)
        self.inputs = [Path(path) for path in inputs]
        self.tables = []
        self.table_only = []

    def _set_variables(self):
        """Sort the columns of df_final by their values, as prep did."""
        if "ID" not in self.df_final.columns:
            raise ValueError("The table has no ID column; prepare it with 'fmriqc prep custom'.")
        self.checkbox_groups, self.vars, self.table_only = classify_columns(self.df_final)
        self.df_final = normalize_columns(self.df_final, self.checkbox_groups, self.vars)

    def _read(self, path):
        suffix = path.suffix.lower()
        if suffix not in (".csv", ".tsv"):
            raise ValueError(f"{path.name}: give a .csv or .tsv file")
        df = read_csv_exact(path, sep="\t" if suffix == ".tsv" else ",", dtype=dict.fromkeys(KEYS, str))
        if "ID" not in df.columns:
            raise ValueError(f"{path.name}: no ID column; name the participant column ID")
        for key in [k for k in KEYS if k in df.columns]:
            df[key] = df[key].str.strip().str.removeprefix(PREFIXES[key]).replace("", np.nan)

        empty = df.index[df["ID"].isna()]
        if len(empty):
            raise ValueError(f"{path.name}: ID is empty on line(s) {', '.join(str(i + 2) for i in empty[:10])}")
        if "run" in df.columns:
            runs = pd.to_numeric(df["run"], errors="coerce")
            wrong = df["run"].notna() & (runs.isna() | (runs % 1 != 0))
            if wrong.any():
                raise ValueError(f"{path.name}: run must be a whole number, not "
                                 f"{', '.join(sorted(set(df.loc[wrong, 'run'])))}")
            df["run"] = runs.astype("Int64")

        keys = [k for k in KEYS if k in df.columns]
        repeated = df[df.duplicated(keys, keep=False)].drop_duplicates(keys)
        if len(repeated):
            listing = "; ".join(_describe_key(row, keys) for _, row in repeated.head(5).iterrows())
            more = f" and {len(repeated) - 5} more" if len(repeated) > 5 else ""
            raise ValueError(f"{path.name}: more than one row for {listing}{more}")
        print(f"Read {path.name}: {len(df)} rows, keyed by {', '.join(keys)}")
        return df

    def _load_raw_data(self):
        self.tables = [(path, self._read(path)) for path in self.inputs]
        owners = {}
        for path, df in self.tables:
            for column in df.columns:
                if column not in KEYS:
                    owners.setdefault(column, []).append(path.name)
        shared = {column: names for column, names in owners.items() if len(names) > 1}
        if shared:
            listing = "; ".join(f"{column} ({', '.join(names)})" for column, names in shared.items())
            raise ValueError(f"Columns in more than one file: {listing}. Keep each column in one file.")

    def _merge(self):
        (first, merged), *rest = self.tables
        names = [first.name]
        for path, df in rest:
            keys = [k for k in KEYS if k in merged.columns and k in df.columns]
            result = merged.merge(df, on=keys, how="outer", indicator=True)
            counts = result["_merge"].value_counts()
            print(f"Merged {path.name} on {', '.join(keys)}: {counts['both']} rows matched, "
                  f"{counts['left_only']} only in {', '.join(names)}, {counts['right_only']} only in {path.name}")
            # An outer join keeps both sides when nothing matches, so only the matched count shows a mismatch
            if counts["both"] == 0:
                print(f"WARNING: no row of {path.name} matched! The files probably label participants differently.")
                for key in keys:
                    print(f"  {key}: {', '.join(names)}={sorted(merged[key].dropna().astype(str).unique())[:8]} "
                          f"vs {path.name}={sorted(df[key].dropna().astype(str).unique())[:8]}")
            merged = result.drop(columns="_merge")
            names.append(path.name)
        keys = [k for k in KEYS if k in merged.columns]
        return merged[keys + [c for c in merged.columns if c not in keys]]

    def _clean_data(self):
        df = self._merge()
        ratings, metrics, table_only = classify_columns(df)
        self.df_final = normalize_columns(df, ratings, metrics)
        self.checkbox_groups, self.vars, self.table_only = ratings, metrics, table_only

        print(f"\nRatings (filter and heatmap): {', '.join(ratings) or 'none'}")
        print(f"Metrics (slider): {', '.join(metrics) or 'none'}")
        print(f"Table only: {', '.join(table_only) or 'none'}")
        for column in table_only:
            print(f"  {column}: {odd_values(df[column])}")
        if any(not _present(df[column]).empty for column in table_only):
            print("To filter on a column of ratings, change its values to good, other or bad and run this "
                  "command again.")

    def _sort_by_id(self):
        """By ID, then session and run; numeric labels in numeric order."""
        df = self.df_final
        keys = [k for k in KEYS if k in df.columns]
        order = {f"_{k}_num": pd.to_numeric(df[k], errors="coerce") for k in keys}
        by = [c for k in keys for c in (f"_{k}_num", k)]
        self.df_final = (df.assign(**order).sort_values(by, na_position="last", kind="stable")
                         .drop(columns=list(order)).reset_index(drop=True))
