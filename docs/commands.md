# Commands

Each command's options are explained on the page linked below. In the terminal, `--help` after a command lists them, such as `fmriqc prep fmriprep --help`.

| Command | What it does | Options |
|---|---|---|
| `fmriqc rating afni` | Opens the AFNI QC reports to rate | [Rating AFNI output](rating-afni.md#command) |
| `fmriqc rating fmriprep` | Opens the fMRIPrep reports in the rating page | [Rating fMRIPrep output](rating-fmriprep.md#command) |
| `fmriqc prep afni` | Makes `df_final.csv` from AFNI output | [Preparing the table](prep.md#afni) |
| `fmriqc prep fmriprep` | Makes `df_final.csv` from MRIQC metrics and fMRIPrep ratings | [Preparing the table](prep.md#fmriprep) |
| `fmriqc prep custom` | Makes `df_final.csv` from your own tables | [Your own tables](custom.md#preparing-the-table) |
| `fmriqc dashboard afni` | Opens the dashboard for AFNI data | [Dashboard](dashboard.md) |
| `fmriqc dashboard fmriprep` | Opens the dashboard for fMRIPrep data | [Dashboard](dashboard.md) |
| `fmriqc dashboard custom` | Opens the dashboard for your own tables | [Your own tables](custom.md#opening-the-dashboard) |
| `fmriqc config afni` | Writes the default AFNI config file, to edit | [Config file](config.md#writing-a-copy-of-the-defaults) |
| `fmriqc config fmriprep` | Writes the default fMRIPrep config file, to edit | [Config file](config.md#writing-a-copy-of-the-defaults) |
