# Change Log

## [Unreleased]


## [2.0.0] - 2026-11-25
### Added
- A **Settings** tab in the dashboard: choose the metrics shown and their order, edit labels and thresholds, and see how many runs each threshold would hide before saving. Saved changes apply right away, without restarting the dashboard.
- **Table only** columns in the Settings tab, shown in the table without a filter.
- Settings are saved as `afni_config.json` or `fmriprep_config.json` next to `df_final.csv` and used again next time; `--config FILE` uses another file. The terminal shows which file is used.
- **Download config** in the Settings tab, and `fmriqc config afni|fmriprep --output FILE`, give a settings file to edit, share or reuse.

### Changed
- **Thresholds are set in the settings file instead of the code.** Config files from 1.x no longer work; `fmriqc config` writes a new one.
- **Only runs rated bad are hidden by default.** Runs rated other stay visible and are yellow in the heatmap; tick boxes under each metric choose which ratings to show.
- A few runs are rated or hidden differently than in 1.0: values are no longer rounded before rating, runs with a `flip_guess` other than 0 are hidden, and a censored fraction of exactly 0.2 counts as bad.
- fMRIPrep runs are rated on `fd_perc` and `fd_mean` only; `tsnr` and `gcor` no longer have thresholds.
- `fmriqc prep` writes only `df_final.csv`, at full precision, with every numeric metric from MRIQC or the AFNI review file.
- The table shows the IDs, the metrics chosen in the Settings tab and the ratings, with three decimals; downloads keep every column at full precision.
- Heatmap rows use the sidebar labels and order.
- The dashboard responds faster: plots are drawn only on the Plots tab, and heatmaps are faster on large tables.
- Reloading the page keeps the open tab.

### Fixed
- The fMRIPrep dashboard's sidebar no longer lists AFNI's thresholds.
- A metric with the same value in every run no longer flattens the other metrics in the lollipop chart.
- With Dash 4, the boxes under each slider no longer cover the tick boxes below.

### Removed
- `lollipop_chart_data.csv` and the dashboards' `--lollipop-file` option.
- The old standalone scripts in `examples/scripts`, replaced by the `fmriqc` commands.
- `seconds_per_run` from the default fMRIPrep metrics; `fmriqc prep` never produced it.
- For Python users: `assign_afni_status` and `assign_fmriprep_status` (use `assign_status`), and the `lollipop_file` argument of `from_saved_data`.


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
