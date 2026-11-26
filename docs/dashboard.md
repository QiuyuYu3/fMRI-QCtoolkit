# Dashboard

```bash
fmriqc dashboard afni --data-file /PATH/QC/df_final.csv --task rest
fmriqc dashboard fmriprep --data-file /PATH/QC/df_final.csv --task rest
```

`--data-file`
: The `df_final.csv` written by `fmriqc prep`.

`--task`
: The task name, used in the name of downloaded files.

`--config`
: Optional. The file that holds your settings (see [Config file](config.md#where-the-settings-are-kept)). Without it, the dashboard uses `afni_config.json` or `fmriprep_config.json` in the folder of `--data-file`.

`--host`
: Optional. The address to listen on; see [The token](opening-pages.md#the-token) before changing it.

The terminal prints the settings file in use and a link to open (see [Opening the pages](opening-pages.md)). The dashboard has a sidebar of filters on the left and three tabs: **Table**, **Plots** and **Settings**. The filters apply to the table and the heatmaps.

## Ratings of the metrics

Each metric with thresholds rates every run **good**, **other** or **bad**, and **NA** when the value is missing. The thresholds come from the settings file; [Default thresholds](thresholds.md) lists the ones the toolkit starts with, and the [Settings tab](settings.md) changes them. Other means "look again": it is neither good nor bad.

When the dashboard opens, runs rated bad on any metric are hidden, and runs rated other are shown and marked yellow in the heatmap.

## Sidebar

```{image} images/sidebar.png
:alt: The sidebar with the thresholds in force, a rated metric and an unrated one
:width: 280px
```

The top of the sidebar lists the thresholds in force. Below it, each metric has:

- **a slider** that keeps only the runs whose value lies in the range. It starts at the full range of the data, so at first it hides nothing. The numbers above the track mark the good threshold (green) and the bad threshold (red).
- **tick boxes** for the ratings to show: good, other, bad and NA. Bad starts unticked; tick it to bring those runs back. A metric without a bad rule has no bad box, and one without a good rule has no other box, as in the AFNI example below.
- for a metric without thresholds, a single **Include NA** box, which keeps runs where the value is missing.

```{image} images/afni_sidebar.png
:alt: AFNI's TSNR, which has only a good threshold, and Flip Guess, which has only a bad one
:width: 280px
```

At the bottom of the sidebar, a list for each rating column (each section of the fMRIPrep report, or each APQC block) keeps only the runs with the ratings you choose.

A run is shown only if it passes every filter.

## Table

![The Table tab with two rows selected](images/table.png)

The table shows the runs that pass the filters: the ID, session and run, the metrics in the order of the Settings tab, any columns you add under Table only, and the ratings. Numbers are shown with three decimals; the data keep full precision. Click a column name to sort by it, and use **Rows per page** to see more rows at once.

Tick the box at the start of a row to select it. **Select All (filtered)** selects every row that passes the filters, and **Clear** clears the selection. The selected rows appear under **Selected Rows**, and **Download Selected Data** saves them as `<task>_MRI_QC_subj.csv`, with every column of `df_final.csv` at full precision. A selection stays when you change the filters, as long as the row is still shown.

## Plots

The Plots tab is drawn when you open it, and redrawn when the filters change while it is open.

```{image} images/heatmaps.png
:alt: The heatmaps of the Plots tab
:width: 600px
```

**Quantitative Metrics** has one row per metric with thresholds and one column per run: green for good, yellow for other, red for bad and gray for NA. **Qualitative Ratings** shows the ratings the same way, one row per section of the report. fMRIPrep runs are grouped by session and run; hover over a cell to see the run, the metric and its rating. Both heatmaps follow the filters.

For AFNI, the quantitative heatmap also has one row per stimulus class for the fraction of TRs censored:

```{image} images/afni_heatmaps.png
:alt: The heatmaps of an AFNI task dataset
:width: 620px
```

![The lollipop chart of standardized metrics](images/lollipop.png)

**Standardized Metrics Overview** is a lollipop chart of the main metrics. Each metric is converted to z-scores across all runs (its mean is 0 and its standard deviation 1), so metrics on different scales can be compared, and a run far from 0 stands out from the rest of the sample. Each color is one metric, and each lollipop is one run. A metric with the same value in every run is drawn at 0. The chart always shows every run, whatever the filters.
