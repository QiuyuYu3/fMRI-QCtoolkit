# Change Log

## [Unreleased]


## [1.0.0] - 2026-10-24
### Security
- The rating interface and dashboards now require a per-session token. The terminal prints a link containing it; requests without it get "Access denied". This keeps other users on a shared machine (such as an HPC login node) out of the pages and the ratings.
- Requests whose Host header is not a loopback name are refused while the server is bound to localhost, which blocks DNS rebinding from web pages.
- Subject labels in rating URLs and saves must be alphanumeric BIDS labels. Before, a crafted label could read `.html` files and write ratings outside the input and output directories on Windows.
- `qc rating afni` no longer runs `open_apqc.py` through a shell, so paths with spaces or shell characters are passed as-is.
- `qc dashboard --debug` is refused on a non-loopback `--host`, and a non-loopback host prints a warning.

### Fixed
- Ratings are no longer lost when one session contains more than one task.
- Ratings are no longer lost when a task has several acquisitions, directions, or echoes.
- Run numbers in the exported CSV now match the run labels shown in the fMRIPrep report.
- Fieldmap panels are no longer counted as tasks.
- Subject IDs keep their leading zeros; `sub-0030` and `sub-30` are no longer the same subject.
- Subject IDs are no longer truncated when they start with a letter from `sub-` (`s001` became `001`).
- Non-numeric subject labels such as `sub-A01` no longer crash `qc prep`.
- `qc prep` now warns when the ratings and MRIQC have no records in common.
- The dashboard heatmaps no longer crash on non-numeric subject labels (`sub-A01`) or session labels (`ses-pre`), or with pandas 3.
- Changing a dashboard filter no longer moves the table selection to another run or session of the same subject, so "Download Selected Data" exports the runs that were selected.
- fMRIPrep ratings are no longer lost when a rating CSV cannot be written (for example while it is open in Excel); the save reports the locked file.
- Ratings for an fMRIPrep report with only anatomical items can now be saved.
- Two fMRIPrep report groups no longer share one rating when an acquisition, direction, or run label appears on only some of a task's groups.
- On Windows, a second `qc dashboard` or `qc rating fmriprep` no longer picks a port that another one is already serving, which showed up as "Access denied".
- `qc dashboard --host 0.0.0.0` and IPv6 hosts now print a link that opens.
- A rating that cannot be saved because the server restarted now says to open the new link, instead of reporting a network error.

### Changed
- `qc rating afni --afni-path` no longer defaults to a cluster-specific path; `open_apqc.py` is taken from `$PATH` unless the option is given.
- Session labels are kept as written (`ses-pre`, `ses-V1`) instead of being forced to numbers.
- Subject IDs are kept as labels rather than numbers throughout.
- Dependencies now have minimum versions (Dash 2.17 to 4.x, pandas 2.1, NumPy 1.26, Plotly 5.20, Flask 3.0, Typer 0.12).

### Added
- First release on PyPI: `pip install fmri-qctoolkit`.
- `qc rating fmriprep --no-browser` prints the links without opening browser tabs. Tabs are also not opened on Linux when no display is available.
- Unit tests for the dashboard's heatmap data.

### Removed
- `BaseDataProcessor.from_files`, unused and broken since it was added.
- The unused `flask-cors` dependency.

### Notes
- Anatomical items (T1mask / Norm / SurfRecon) can show more than one image if the subject was processed by fMRIPrep more than once. See the README.
- Ratings for a task split by acquisition or direction are saved but not yet shown in the dashboard. The rating app says so when the subject is opened, and `qc prep` lists the files it skips.


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
