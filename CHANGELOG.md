# Change Log

## [Unreleased]


## [1.0.0] - 2026-09-05
### Fixed
- Ratings are no longer lost when one session contains more than one task.
- Ratings are no longer lost when a task has several acquisitions, directions, or echoes.
- Run numbers in the exported CSV now match the run labels shown in the fMRIPrep report.
- Fieldmap panels are no longer counted as tasks.
- Subject IDs keep their leading zeros; `sub-0030` and `sub-30` are no longer the same subject.
- Subject IDs are no longer truncated when they start with a letter from `sub-` (`s001` became `001`).
- Non-numeric subject labels such as `sub-A01` no longer crash `qc prep`.
- `qc prep` now warns when the ratings and MRIQC have no records in common.

### Changed
- Session labels are kept as written (`ses-pre`, `ses-V1`) instead of being forced to numbers.
- Subject IDs are kept as labels rather than numbers throughout.

### Added
- Unit tests for the dashboard's heatmap data.

### Removed
- `BaseDataProcessor.from_files`, unused and broken since it was added.

### Notes
- Anatomical items (T1mask / Norm / SurfRecon) can show more than one image if the subject was
  processed by fMRIPrep more than once. See the README.
- Ratings for a task split by acquisition or direction are saved but not yet shown in the
  dashboard. The rating app says so when the subject is opened, and `qc prep` lists the files
  it skips.


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
