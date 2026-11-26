# Quick start

This page runs the three steps with the options you need most. Replace the paths in capitals with your own. Each step has its own page with every option and the details.

## 1. Rate

For AFNI, open the APQC reports of a few participants (AFNI must be available, see [Rating AFNI output](rating-afni.md)):

```bash
fmriqc rating afni --input-dir /PATH/AFNI_derivatives --subjects "001,002" --task rest --prefix sub-
```

For fMRIPrep, open the fMRIPrep reports and save the ratings in a folder of your choice:

```bash
fmriqc rating fmriprep --input-dir /PATH/fmriprep --subjects "001,002" --output-dir /PATH/ratings
```

Each report opens in a browser tab. Rate every section, then press Ctrl+C in the terminal to stop.

## 2. Prepare

Collect the ratings and the metrics into `df_final.csv`:

```bash
fmriqc prep afni --input-dir /PATH/AFNI_derivatives --task rest --prefix sub- --output-dir /PATH/QC
fmriqc prep fmriprep --bold-file /PATH/mriqc/group_bold.tsv --rating-dir /PATH/ratings --task rest --output-dir /PATH/QC
```

The last lines in the terminal show the command that opens the dashboard on this table.

## 3. View

```bash
fmriqc dashboard afni --data-file /PATH/QC/df_final.csv --task rest
fmriqc dashboard fmriprep --data-file /PATH/QC/df_final.csv --task rest
```

The terminal prints a link such as `http://127.0.0.1:5003/?token=...`. Open it in your browser. On an HPC cluster, first forward the port as described in [Opening the pages](opening-pages.md).

Runs rated bad on any metric are hidden when the dashboard opens. The [Dashboard](dashboard.md) page explains the filters, the table and the plots, and [Settings tab](settings.md) explains how to change the thresholds.

## Try it on example data

From a clone of the repository (see [Installation](installation.md#from-the-repository)), steps 2 and 3 run on a small made-up fMRIPrep dataset of five participants with three runs each:

```bash
fmriqc prep fmriprep --bold-file examples/example_data/fmriprep/group_bold.tsv --rating-dir examples/example_data/fmriprep/ratings --task rest --output-dir example_QC
fmriqc dashboard fmriprep --data-file example_QC/df_final.csv --task rest
```
