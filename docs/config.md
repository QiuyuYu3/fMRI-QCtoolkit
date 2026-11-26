# Config file

The settings of the [Settings tab](settings.md) live in a JSON file. Most users never open it: the Settings tab writes it for them. This page is for those who want to edit it by hand, share it, or keep several.

## Where the settings are kept

- Without `--config`, the dashboard reads and saves `afni_config.json` or `fmriprep_config.json` in the folder of `--data-file`. The next time you open the same data, it uses that file again.
- With `--config FILE`, it reads and saves `FILE` instead, for example to use one file for several datasets.
- If the file does not exist yet, the dashboard starts from the package's defaults and creates the file the first time you save.

When the dashboard starts, the terminal prints the file it uses, with a note when the file does not exist yet.

```bash
fmriqc dashboard fmriprep --data-file /PATH/QC/df_final.csv --task rest --config my_fmriprep_config.json
```

## Writing a copy of the defaults

`fmriqc config` writes the package's default file, to start editing from:

```bash
fmriqc config fmriprep --output my_fmriprep_config.json
```

It does not overwrite an existing file unless you add `--force`, so that edited thresholds are not replaced by the defaults by accident. A file edited by hand takes effect when the dashboard starts again. The defaults are also on GitHub: [AFNI](https://github.com/QiuyuYu3/fMRI-QCtoolkit/blob/main/fMRI_QCtoolkit/dashboard/afni_config.json), [fMRIPrep](https://github.com/QiuyuYu3/fMRI-QCtoolkit/blob/main/fMRI_QCtoolkit/dashboard/fmriprep_config.json).

## Format

Each metric is one entry under `metrics`, keyed by its column in `df_final.csv`:

```json
{
  "metrics": {
    "cens_frac":       {"label": "Censor Fraction",       "good": "< 0.15", "bad": ">= 0.2"},
    "TSNR":            {"label": "TSNR Average",          "good": "> 150"},
    "flip_guess":      {"label": "Flip Guess",                              "bad": "!= 0",   "step": 1},
    "frac_TRs_cens_*": {"label": "Fraction TRs Censored",                   "bad": ">= 0.2"},
    "anat/EPI_mask_Dice_coef": {"label": "Anat/EPI Mask Dice"}
  },
  "table_columns": ["TR", "max_motion_displacement"]
}
```

`label`
: The name shown in the sidebar, the table and the heatmap. Defaults to the column name.

`good` and `bad`
: An operator (`>`, `>=`, `<`, `<=`, `==`, `!=`) followed by a number. A run is bad if it meets the bad rule, good if it meets the good rule, and otherwise gets the `otherwise` level; a missing value is NA. The two rules must not overlap.

`otherwise`
: Optional: `good`, `other` or `bad`, the rating of a run that meets neither rule. Without it, such a run is other when there is a good rule and good when there is only a bad rule.

`step`
: Optional. The slider's step; by default it follows the range of the data.

`table_columns`
: Optional. Columns shown in the table after the metrics, without a slider or heatmap row (the Table only list of the Settings tab).

A metric with neither rule nor `otherwise` is shown and can be filtered, but it is not rated and has no heatmap row.

A key with `*` covers every matching column, so `frac_TRs_cens_*` gives one entry per stimulus class, each labeled with its column name.

## Rules of the file

- Metrics appear in the sidebar, the table and the heatmap in the order of the file.
- Metrics missing from the data are skipped, and the dashboard lists them when it starts.
- The file replaces the defaults as a whole: metrics you leave out are not shown.
- When the Settings tab saves, the file it replaces is kept as `<name>.bak`.
- A file with a mistake stops the dashboard with a message that names the entry and the problem, for example two rules that overlap.
- Files from version 1.x, and files that still use an `other` rule, no longer work; the message says how to change them, and `fmriqc config` writes a file in the current format.
