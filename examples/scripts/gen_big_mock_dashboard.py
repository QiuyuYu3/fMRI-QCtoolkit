"""
Generate a large mock dashboard dataset (df_final.csv + lollipop_chart_data.csv)
to stress-test the heatmap with many subjects.

Usage:
    python gen_big_mock_dashboard.py --n-subjects 150 --output-dir examples/example_data/fmriprep_big
"""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline

QUAL_COLS = ["Align", "BOLD", "CompCor", "Corr", "Final", "Norm", "SDC", "SurfRecon", "T1mask", "Variance"]


def build_df_final(n_subjects: int, runs_per_subject: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(1, n_subjects + 1):
        for run in range(1, runs_per_subject + 1):
            row = {
                "ID": s,
                "session": 1,
                "run": run,
                "modality": "rest",
                "dummy_trs": rng.integers(3, 8),
                "fd_perc": rng.uniform(5, 35),
                "gcor": rng.uniform(0.05, 0.35),
                "gsr_x": rng.uniform(0.01, 0.06),
                "gsr_y": rng.uniform(0.01, 0.06),
                "aor": rng.uniform(0.1, 0.4),
                "aqi": rng.uniform(0.3, 0.8),
                "dvars_nstd": rng.uniform(0.8, 1.5),
                "tsnr": rng.uniform(80, 320),
                "fd_mean": rng.uniform(0.1, 0.45),
                "spacing_tr": rng.uniform(1.5, 3.0),
            }
            for col in QUAL_COLS:
                # ~12% missing, rest split across good/bad/other
                row[col] = rng.choice([np.nan, "good", "bad", "other"], p=[0.12, 0.5, 0.25, 0.13])
            rows.append(row)

    ordered = ["ID", "session", "run"] + QUAL_COLS + [
        "modality", "dummy_trs", "fd_perc", "gcor", "gsr_x", "gsr_y",
        "aor", "aqi", "dvars_nstd", "tsnr", "fd_mean", "spacing_tr",
    ]
    return pd.DataFrame(rows)[ordered]


def main():
    parser = argparse.ArgumentParser(description="Generate a large mock dashboard dataset.")
    parser.add_argument("--n-subjects", type=int, default=150)
    parser.add_argument("--runs-per-subject", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("examples/example_data/fmriprep_big"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = build_df_final(args.n_subjects, args.runs_per_subject, args.seed)

    # Reuse the real lollipop logic from the pipeline
    p = FMRIPrepPipeline.__new__(FMRIPrepPipeline)
    p.df_final = df
    p._set_variables()
    p._prepare_lollipop_data([v for v in p.vars if v in df.columns])

    df_path = args.output_dir / "df_final.csv"
    lollipop_path = args.output_dir / "lollipop_chart_data.csv"
    df.to_csv(df_path, index=False)
    p.lollipop_chart_data.to_csv(lollipop_path, index=False)

    df_posix = df_path.as_posix()
    lollipop_posix = lollipop_path.as_posix()
    print(f"Wrote {len(df)} rows ({args.n_subjects} subjects x {args.runs_per_subject} runs) to:")
    print(f"  {df_posix}")
    print(f"  {lollipop_posix}")
    print(f"\nLaunch with:\n  qc dashboard fmriprep --data-file {df_posix} --lollipop-file {lollipop_posix} --task rest")


if __name__ == "__main__":
    main()
