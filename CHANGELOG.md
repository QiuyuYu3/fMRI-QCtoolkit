# Change Log

## [Unreleased]


## [2.0.0] - 2026-11-25
### Changed
- **`fmriqc prep` writes only `df_final.csv`, at full precision.** The dashboard computes the lollipop chart from it when it loads, so `lollipop_chart_data.csv` is gone and values are no longer rounded to three decimals on disk.
- **Thresholds live in the dashboard config.** Each metric is one line in `afni_config.json` or `fmriprep_config.json`, with an optional label and slider step and `other`/`bad` rules such as `">= 0.2"`. The heatmap colors and the default filters both read them, so changing a threshold changes both. Config files from 1.x no longer work; `fmriqc config` writes the new format.
- **By default only runs rated bad are hidden.** Runs rated other are shown and colored yellow in the heatmap, so more runs are shown by default than in 1.0. Each rated metric has good / other / bad / NA tick boxes in place of "Include NA", and its slider starts at the full range.
- Runs with a `flip_guess` other than 0 are hidden by default; 1.0 showed them.
- Runs whose fraction of TRs censored for a stimulus class is exactly 0.2 are hidden by default; 1.0 showed them.
- Ratings use the unrounded values, so a value within 0.0005 of a threshold can be rated differently than in 1.0 (a censor fraction of 0.1496 is now good, not other).
- fMRIPrep's `tsnr` and `gcor` no longer have thresholds: they are not colored and not in the heatmap, but can still be filtered with their sliders. fMRIPrep runs are rated on `fd_perc` and `fd_mean` only, and a `gcor` above 0.15 no longer hides a run by default.
- The sidebar lists the thresholds of the pipeline shown; the fMRIPrep dashboard used to show AFNI's.
- Heatmap rows use the sidebar labels and follow the config order from the top. The AFNI heatmap of a task has a row for each fraction-of-TRs-censored column.
- The table shows numbers with three decimals; its data and downloads keep full precision.
- The Plots tab is drawn only while it is open, and its heatmaps are redrawn only when the filtered rows change, so a filter change on the Table tab no longer waits for the plots. The lollipop chart is drawn once, when the Plots tab first opens.
- The heatmaps are drawn several times faster on large tables.
- Select All and Clear only change the selection; they no longer refilter the table and redraw the plots.
- `fmriqc prep fmriprep` keeps every numeric metric of `group_bold.tsv` in `df_final.csv` instead of a fixed eleven, so any of them can be added to the dashboard, and an MRIQC output without one of the eleven no longer stops it.
- The table shows the ID, session and run columns, the metrics in the sidebar and the ratings; the other columns start hidden and **Toggle Columns** shows them. Downloads keep every column.
- Reloading the dashboard keeps the tab that was open.

### Fixed
- With Dash 4, the value boxes under each sidebar slider no longer cover the first tick box below them.

### Added
- A **Thresholds** tab in both dashboards. It edits the labels, rules and slider steps, adds, removes and reorders metrics, and counts the runs each metric would rate good, other, bad and NA before anything is saved. Save writes the `--config` file, keeps the previous version as `<name>.bak`, and reloads the page with the new thresholds, without restarting the dashboard.
- `--config FILE` for both dashboard commands, to use your own thresholds. The file may not exist yet: the dashboard then starts from the default and creates it on the first save.
- `fmriqc config afni|fmriprep --output FILE` writes the default config to edit. It refuses to overwrite an existing file unless `--force` is given.
- The dashboard prints the config it uses when it starts, and lists the config metrics missing from the data.

### Removed
- The `--lollipop-file` option of both dashboard commands, and the `lollipop_file` argument of `from_saved_data`.
- `assign_afni_status` and `assign_fmriprep_status`, replaced by `assign_status`.
- The early standalone scripts in `examples/scripts` (`dash/`, the AFNI and fMRIPrep scripts in `data_prep/`, the two `*_dataprep_dash.py` scripts and `afni_QC_shinyR.R`), which the `fmriqc` commands replace.


## [1.0.0] - 2026-10-24
### Security
- The rating interface and dashboards now require a per-session token. The terminal prints a link containing it; requests without it get "Access denied". This keeps other users on a shared machine (such as an HPC login node) out of the pages and the ratings.
- Requests whose Host header is not a loopback name are refused while the server is bound to localhost, which blocks DNS rebinding from web pages.
- Subject labels in rating URLs and saves must be alphanumeric BIDS labels. Before, a crafted label could read `.html` files and write ratings outside the input and output directories on Windows.
- `fmriqc rating afni` no longer runs `open_apqc.py` through a shell, so paths with spaces or shell characters are passed as-is.
- `fmriqc dashboard --debug` is refused on a non-loopback `--host`, and a non-loopback host prints a warning.

### Fixed
- Ratings are no longer lost when one session contains more than one task.
- Ratings are no longer lost when a task has several acquisitions, directions, or echoes.
- Run numbers in the exported CSV now match the run labels shown in the fMRIPrep report.
- Fieldmap panels are no longer counted as tasks.
- Subject IDs keep their leading zeros; `sub-0030` and `sub-30` are no longer the same subject.
- Subject IDs are no longer truncated when they start with a letter from `sub-` (`s001` became `001`).
- Non-numeric subject labels such as `sub-A01` no longer crash `fmriqc prep`.
- `fmriqc prep` now warns when the ratings and MRIQC have no records in common.
- The dashboard heatmaps no longer crash on non-numeric subject labels (`sub-A01`) or session labels (`ses-pre`), or with pandas 3.
- Changing a dashboard filter no longer moves the table selection to another run or session of the same subject, so "Download Selected Data" exports the runs that were selected.
- fMRIPrep ratings are no longer lost when a rating CSV cannot be written (for example while it is open in Excel); the save reports the locked file.
- Ratings for an fMRIPrep report with only anatomical items can now be saved.
- Two fMRIPrep report groups no longer share one rating when an acquisition, direction, or run label appears on only some of a task's groups.
- On Windows, a second `fmriqc dashboard` or `fmriqc rating fmriprep` no longer picks a port that another one is already serving, which showed up as "Access denied".
- `fmriqc dashboard --host 0.0.0.0` and IPv6 hosts now print a link that opens.
- A rating that cannot be saved because the server restarted now says to open the new link, instead of reporting a network error.
- `fmriqc prep afni` no longer keeps only one session when `--task` matches a subject in several sessions; it stops and lists the matches so `--task` can be narrowed to one session.
- `fmriqc prep afni` now accepts alphanumeric subject labels (`sub-A01`) and treats `--prefix` literally.

### Changed
- **The command is now `fmriqc` instead of `qc` (`fmriqc prep`, `fmriqc rating`, `fmriqc dashboard`).**
- `fmriqc rating afni --afni-path` no longer defaults to a cluster-specific path; `open_apqc.py` is taken from `$PATH` unless the option is given.
- Session labels are kept as written (`ses-pre`, `ses-V1`) instead of being forced to numbers.
- Subject IDs are kept as labels rather than numbers throughout.
- The dashboard heatmaps redraw about three times faster after a filter change.
- Dependencies now have minimum versions (Dash 2.17 to 4.x, pandas 2.1, NumPy 1.26, Plotly 5.20, Flask 3.0, Typer 0.16).

### Added
- First release on PyPI: `pip install fmri-qctoolkit`.
- `fmriqc rating fmriprep --no-browser` prints the links without opening browser tabs. Tabs are also not opened on Linux when no display is available.
- Unit tests for the dashboard's heatmap data.

### Removed
- `BaseDataProcessor.from_files`, unused and broken since it was added.
- The unused `flask-cors` dependency.

### Notes
- Anatomical items (T1mask / Norm / SurfRecon) can show more than one image if the subject was processed by fMRIPrep more than once. See the README.
- Ratings for a task split by acquisition or direction are saved but not yet shown in the dashboard. The rating app says so when the subject is opened, and `fmriqc prep` lists the files it skips.


## [0.11.0] - 2026-06-12
### Added
- "Select All (filtered)" and "Clear" buttons in the dashboard table.
- Horizontal scroll for the heatmap when there are many subjects.

### Changed
- fMRIPrep rating now reloads from a JSON sidecar; CSV is kept as export only.
- Heatmap redrawn as a discrete square-marker grid.
- Lollipop chart split into stacked panels by session and run.

### Removed
- CSV-column reverse-mapping on rating reload.


## [0.10.0-beta.1] - 2025-11-04
### Added
- Added a test script for fMRIPrep rating.

### Changed
- Updated heatmap grouping methods.
- Improved fMRIPrep preprocessing program: dropped missing values and added common modules.


## [0.10.0-alpha.1] - 2025-10-27
### Added
- Support for handling `session` in fMRIPrep front end; defaults to `1` if session/run not detected.
- Data simulation module.

### Changed
- `gsr_x` and `gsr_y` now remain unchanged instead of being averaged.
- Aggregation method for MRIQC and fMRIPrep scoring changed from `inner` to `outer`.

### Notes
- Additional tests needed for session detection feature in fMRIPrep Rating.
