# Change Log

## [Unreleased]
### Fixed
- fMRIPrep rating: module ids now name the task (and any acquisition / direction / echo that
  varies inside a task) whenever a session holds more than one report group of the same shape.
  Two tasks in one session that both carried BIDS run numbers used to collide on the same ids,
  and the second task's ratings were written to its CSV as `NA`.
- fMRIPrep rating: `Reports for:` headings are parsed generically, so entities between task and
  run (`acquisition`, `ceagent`, `reconstruction`, `direction`, `echo`) no longer merge separate
  report groups into one. Each value gets its own CSV, e.g. `sub-001_ses-01_rest_acq-seq.csv`.
- fMRIPrep rating: reportlet div ids are no longer parsed. They are ordered alphabetically by
  entity name, so ids beginning with `acquisition-` were never matched.
- fMRIPrep rating: fieldmap report groups, which carry no task, are skipped instead of
  consuming a run number.

### Changed
- `parse_tasks_from_html` returns one entry per output CSV, with `runs` holding the BIDS run
  labels of that unit rather than a run count.
- Heatmap row building moved out of the dashboard callback into
  `BaseDashboard.quantitative_heatmap_rows` / `qualitative_heatmap_rows`, which are now tested.

### Added
- `tests/test_dashboard.py`, the first coverage of `dashboard/base_app.py`.

### Notes
- Anatomical modules (T1mask / Norm / SurfRecon) may show multiple figures under one rating
  widget when a subject's `figures/` directory holds output from more than one fMRIPrep run.


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
