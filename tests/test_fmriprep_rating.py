"""
Unit tests for fmriprep_rating_app module.
Focus on field matching across parse_tasks, process_html, load_ratings, and save_ratings.
"""

import os
import pytest
import tempfile
import csv
import json
from pathlib import Path
from fMRI_QCtoolkit.dashboard.fmriprep_rating_app import FMRIPrepRatingApp


# ============================================================================
# Mock HTML Data
# ============================================================================

HTML_WITH_SESSION = """
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<nav class="navbar">Summary</nav>

<h2>Anatomical</h2>
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
<h3 class="run-title">Spatial normalization of the anatomical T1w reference</h3>
<h3 class="run-title">Surface reconstruction</h3>

<h2>Reports for: session <span>01</span>, task <span>rest</span>, run <span>1</span></h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
<h3 class="run-title">BOLD Summary</h3>

<h2>Reports for: session <span>01</span>, task <span>rest</span>, run <span>2</span></h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
<h3 class="run-title">BOLD Summary</h3>

<h2>Reports for: session <span>02</span>, task <span>motor</span></h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

</body>
</html>
"""

HTML_NO_SESSION = """
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<nav class="navbar">Summary</nav>

<h2>Anatomical</h2>
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
<h3 class="run-title">Spatial normalization of the anatomical T1w reference</h3>

<h2>Reports for: task <span>localizer</span>, run <span>1</span></h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

<h2>Reports for: task <span>localizer</span>, run <span>2</span></h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

<h2>Reports for: task <span>rest</span></h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

</body>
</html>
"""

HTML_MIXED = """
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<nav class="navbar">Summary</nav>

<h2>Anatomical</h2>
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>

<h2>Reports for: session <span>01</span>, task <span>rest</span>, run <span>1</span></h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

<h2>Reports for: task <span>localizer</span></h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">BOLD Summary</h3>

</body>
</html>
"""

HTML_DIV_WITH_RUN = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_subject-test_suffix-dseg">
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
</div>

<div id="datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2>Reports for: session <span>01</span>, task <span>rest</span>, run <span>1</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
</div>

<div id="datatype-figures_desc-sdc_run-2_session-01_subject-test_suffix-bold_task-rest">
<h2>Reports for: session <span>01</span>, task <span>rest</span>, run <span>2</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
<h3 class="run-title">BOLD Summary</h3>
</div>

</body></html>
"""

HTML_DIV_NO_RUN_MULTITASK = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_subject-test_suffix-dseg">
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
</div>

<div id="datatype-figures_desc-sdc_session-01_subject-test_suffix-bold_task-MID1">
<h2>Reports for: session <span>01</span>, task <span>MID1</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
</div>

<div id="datatype-figures_desc-sdc_session-01_subject-test_suffix-bold_task-MID2">
<h2>Reports for: session <span>01</span>, task <span>MID2</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
</div>

<div id="datatype-figures_desc-sdc_session-01_subject-test_suffix-bold_task-rest">
<h2>Reports for: session <span>01</span>, task <span>rest</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">Brain mask and (anatomical/temporal) CompCor ROIs</h3>
</div>

</body></html>
"""

# Two tasks in one session, both carrying BIDS run numbers in the div id.
# Mirrors real fMRIPrep output: the "Reports for:" h2 sits inside the group's
# first reportlet div (desc-summary, which has no run-title), modules follow in
# their own divs. Tasks are ordered alphabetically, as nireports emits them.
HTML_MULTITASK_WITH_RUNS = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_subject-test_suffix-dseg">
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
</div>

<div id="datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-nback">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">nback</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-nback">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>
<div id="datatype-figures_desc-coreg_run-1_session-01_subject-test_suffix-bold_task-nback">
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
</div>

<div id="datatype-figures_desc-summary_run-2_session-01_subject-test_suffix-bold_task-nback">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">nback</span>, run <span class="bids-entity">2</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-2_session-01_subject-test_suffix-bold_task-nback">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>
<div id="datatype-figures_desc-coreg_run-2_session-01_subject-test_suffix-bold_task-nback">
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
</div>

<div id="datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>
<div id="datatype-figures_desc-coreg_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
</div>

<div id="datatype-figures_desc-summary_run-2_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, run <span class="bids-entity">2</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-2_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>
<div id="datatype-figures_desc-coreg_run-2_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Alignment of functional and anatomical MRI data (coregistration)</h3>
</div>

</body></html>
"""

# Two acquisitions of one task, each with two runs. `acquisition` sits between
# task and run in the heading, and sorts ahead of `datatype` in the div id --
# both taken from a real fMRIPrep 25.2.5 report (OpenNeuro ds027).
HTML_ACQ_BETWEEN_TASK_AND_RUN = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_subject-test_suffix-dseg">
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
</div>

<div id="acquisition-seq_datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, acquisition <span class="bids-entity">seq</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="acquisition-seq_datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

<div id="acquisition-seq_datatype-figures_desc-summary_run-2_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, acquisition <span class="bids-entity">seq</span>, run <span class="bids-entity">2</span>.</h2>
</div>
<div id="acquisition-seq_datatype-figures_desc-sdc_run-2_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

<div id="acquisition-mb_datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, acquisition <span class="bids-entity">mb</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="acquisition-mb_datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

<div id="acquisition-mb_datatype-figures_desc-summary_run-2_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, acquisition <span class="bids-entity">mb</span>, run <span class="bids-entity">2</span>.</h2>
</div>
<div id="acquisition-mb_datatype-figures_desc-sdc_run-2_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

</body></html>
"""

# Fieldmap groups carry session/run/fmapid but no task, and must not become tasks.
HTML_FIELDMAP_GROUPS = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_desc-anat_fmapid-auto00002_run-1_session-01_subject-test_suffix-fieldmap">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, run <span class="bids-entity">1</span>, fmapid <span class="bids-entity">auto00002</span>.</h2>
<h3 class="run-title">Preprocessed estimation by nonlinear registration to an anatomical scan</h3>
</div>

<div id="datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

</body></html>
"""

# One task whose BIDS run labels are not contiguous (run-1 and run-3). The labels
# must survive into the module ids and CSV columns so `fmriqc prep` can join them
# against the run numbers in MRIQC's group_bold.tsv.
HTML_GAPPED_RUNS = """
<!DOCTYPE html>
<html><body>

<div id="datatype-figures_subject-test_suffix-dseg">
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
</div>

<div id="datatype-figures_desc-summary_run-1_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, run <span class="bids-entity">1</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-1_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

<div id="datatype-figures_desc-summary_run-3_session-01_subject-test_suffix-bold_task-rest">
<h2 class="sub-report-group">Reports for: session <span class="bids-entity">01</span>, task <span class="bids-entity">rest</span>, run <span class="bids-entity">3</span>.</h2>
</div>
<div id="datatype-figures_desc-sdc_run-3_session-01_subject-test_suffix-bold_task-rest">
<h3 class="run-title">Susceptibility distortion correction</h3>
</div>

</body></html>
"""

# ============================================================================
# Mock Rating Data
# ============================================================================

MOCK_RATINGS_WITH_SESSION = {
    "T1mask_run-1": "1",
    "Norm_run-1": "2",
    "Align_ses-01_run-1": "1",
    "BOLD_ses-01_run-1": "2",
    "Final_ses-01_run-1": "1",
    "Align_ses-01_run-2": "2",
    "BOLD_ses-01_run-2": "1",
    "Final_ses-01_run-2": "2",
    "Align_ses-02_run-1": "1",
    "BOLD_ses-02_run-1": "1",
    "Final_ses-02_run-1": "1",
}

MOCK_NOTES_WITH_SESSION = {
    "Align_ses-01_run-1": "Good alignment",
    "BOLD_ses-01_run-2": "Some artifacts",
}

MOCK_RATINGS_NO_SESSION = {
    "T1mask_run-1": "1",
    "Align_task-localizer_run-1": "2",
    "BOLD_task-localizer_run-1": "1",
    "Final_task-localizer_run-1": "2",
    "Align_task-localizer_run-2": "1",
    "BOLD_task-localizer_run-2": "2",
    "Final_task-localizer_run-2": "1",
    "Align_task-rest_run-1": "1",
    "BOLD_task-rest_run-1": "1",
    "Final_task-rest_run-1": "2",
}

MOCK_NOTES_NO_SESSION = {
    "Align_task-localizer_run-1": "First run looks good",
    "BOLD_task-rest_run-1": "Last run has motion",
}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_app():
    """Create temporary FMRIPrepRatingApp instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        output_dir = Path(tmpdir) / "output"
        data_dir.mkdir()
        
        app = FMRIPrepRatingApp(data_dir, output_dir, debug=False)
        yield app


@pytest.fixture
def temp_app_debug():
    """Create temporary FMRIPrepRatingApp instance"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        output_dir = Path(tmpdir) / "output"
        data_dir.mkdir()
        
        app = FMRIPrepRatingApp(data_dir, output_dir, debug=True)
        yield app


# ============================================================================
# Helper Functions
# ============================================================================

def save_ratings_direct(app, participant_id, ratings, notes, html_content):
    """Direct save method for testing (bypasses Flask); mirrors FMRIPrepRatingApp.save_ratings."""
    tasks = app.parse_tasks_from_html(html_content)

    if not tasks:
        raise ValueError("No tasks found")

    all_combined_data = {}

    for task_info in tasks:
        session = task_info['session']
        task_name = task_info['name']

        row_data = {"ID": participant_id}

        for mod in app.COMMON_MODULES:
            frontend_key = f"{mod}_run-1"
            row_data[f"{mod}_1_r"] = ratings.get(frontend_key, "NA")
            row_data[f"{mod}_1_c"] = notes.get(frontend_key, "")

        for run_label, suffix in zip(task_info['runs'], task_info['suffixes']):
            for mod in app.FUNCTIONAL_MODULES + ["Final"]:
                frontend_key = f"{mod}{suffix}"
                row_data[f"{mod}_{run_label}_r"] = ratings.get(frontend_key, "NA")
                row_data[f"{mod}_{run_label}_c"] = notes.get(frontend_key, "")

        name_parts = []
        if session is not None:
            name_parts.append(f"ses-{session}")
        name_parts.append(task_name)
        name_parts += [f"{k}-{v}" for k, v in task_info['extras'].items()]
        csv_prefix = "_".join(name_parts)
        csv_file = app.output_dir / f"sub-{participant_id}_{csv_prefix}.csv"

        with csv_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row_data.keys()))
            writer.writeheader()
            writer.writerow(row_data)

        for key, value in row_data.items():
            if key != "ID":
                all_combined_data[f"{csv_prefix}_{key}"] = value
    
    combined_csv = app.output_dir / f"sub-{participant_id}.csv"
    combined_row = {"ID": participant_id, **all_combined_data}

    with combined_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(combined_row.keys()))
        writer.writeheader()
        writer.writerow(combined_row)

    # JSON sidecar: replicate the frontend payload (all module ids default to NA/"")
    _, modules_by_run = app.process_html_modules(html_content)
    full_ratings = {}
    full_notes = {}
    for group in modules_by_run:
        for mod in group:
            full_ratings[mod['id']] = ratings.get(mod['id'], "NA")
            full_notes[mod['id']] = notes.get(mod['id'], "")

    json_file = app.output_dir / f"sub-{participant_id}.json"
    with json_file.open("w", encoding="utf-8") as f:
        json.dump({"ratings": full_ratings, "notes": full_notes}, f, ensure_ascii=False, indent=2)


def verify_ratings_match(loaded_ratings, expected_ratings):
    """Helper to verify all ratings match."""
    for key, value in expected_ratings.items():
        assert key in loaded_ratings, f"Missing key: {key}"
        assert loaded_ratings[key] == value, f"Mismatch for {key}: expected {value}, got {loaded_ratings[key]}"


def verify_notes_match(loaded_notes, expected_notes):
    """Helper to verify all notes match."""
    for key, value in expected_notes.items():
        assert key in loaded_notes, f"Missing note key: {key}"
        assert loaded_notes[key] == value, f"Note mismatch for {key}"


# ============================================================================
# Tests
# ============================================================================

class TestParseTasksFromHTML:
    """Test parse_tasks_from_html function."""
    
    def test_session_with_multiple_runs(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        assert len(tasks) == 2
        assert (tasks[0]['name'], tasks[0]['session'], tasks[0]['runs']) == ('rest', '01', ['1', '2'])
        assert (tasks[1]['name'], tasks[1]['session'], tasks[1]['runs']) == ('motor', '02', ['1'])
    
    def test_no_session_with_runs(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_NO_SESSION)
        assert len(tasks) == 2
        assert (tasks[0]['name'], tasks[0]['session'], tasks[0]['runs']) == ('localizer', None, ['1', '2'])
        assert (tasks[1]['name'], tasks[1]['session'], tasks[1]['runs']) == ('rest', None, ['1'])
    
    def test_mixed_sessions(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_MIXED)
        assert len(tasks) == 2
        assert (tasks[0]['name'], tasks[0]['session'], tasks[0]['runs']) == ('rest', '01', ['1'])
        assert (tasks[1]['name'], tasks[1]['session'], tasks[1]['runs']) == ('localizer', None, ['1'])
    
    def test_empty_html(self, temp_app):
        tasks = temp_app.parse_tasks_from_html("")
        assert tasks == []


class TestProcessHTMLModules:
    """Test process_html_modules function."""
    
    def test_session_module_ids(self, temp_app):
        processed_html, modules = temp_app.process_html_modules(HTML_WITH_SESSION)
        
        # Check anatomical modules
        anatomical_group = modules[0]
        anatomical_ids = [m['id'] for m in anatomical_group]
        assert all(id in anatomical_ids for id in ['T1mask_run-1', 'Norm_run-1', 'SurfRecon_run-1'])
        
        # Check functional modules
        all_ids = [m['id'] for group in modules for m in group]
        expected_ids = [
            'Align_ses-01_run-1', 'Align_ses-01_run-2', 'Align_ses-02_run-1',
            'Final_ses-01_run-1', 'Final_ses-01_run-2', 'Final_ses-02_run-1'
        ]
        assert all(id in all_ids for id in expected_ids)
    
    def test_no_session_module_ids(self, temp_app):
        processed_html, modules = temp_app.process_html_modules(HTML_NO_SESSION)
        
        all_ids = [m['id'] for group in modules for m in group]
        expected_ids = [
            'Align_task-localizer_run-1', 'Align_task-localizer_run-2', 'Align_task-rest_run-1',
            'Final_task-localizer_run-1', 'Final_task-localizer_run-2', 'Final_task-rest_run-1'
        ]
        assert all(id in all_ids for id in expected_ids)
    
    def test_module_grouping(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_WITH_SESSION)
        
        assert len(modules) > 1
        first_group = modules[0]
        assert any('T1mask' in mod['id'] for mod in first_group)


class TestSaveAndLoadRatings:
    """Test save_ratings and load_existing_ratings"""
    
    def test_roundtrip_with_session(self, temp_app):
        participant_id = "001"
        
        save_ratings_direct(temp_app, participant_id, MOCK_RATINGS_WITH_SESSION, 
                          MOCK_NOTES_WITH_SESSION, HTML_WITH_SESSION)
        
        # Check CSV files created
        assert (temp_app.output_dir / f"sub-{participant_id}_ses-01_rest.csv").exists()
        assert (temp_app.output_dir / f"sub-{participant_id}_ses-02_motor.csv").exists()
        assert (temp_app.output_dir / f"sub-{participant_id}.csv").exists()
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id)
        verify_ratings_match(loaded_ratings, MOCK_RATINGS_WITH_SESSION)
        verify_notes_match(loaded_notes, MOCK_NOTES_WITH_SESSION)
    
    def test_roundtrip_no_session(self, temp_app):
        participant_id = "002"
        
        save_ratings_direct(temp_app, participant_id, MOCK_RATINGS_NO_SESSION,
                          MOCK_NOTES_NO_SESSION, HTML_NO_SESSION)
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id)
        verify_ratings_match(loaded_ratings, MOCK_RATINGS_NO_SESSION)
        verify_notes_match(loaded_notes, MOCK_NOTES_NO_SESSION)
    
    def test_empty_ratings(self, temp_app):
        participant_id = "003"
        save_ratings_direct(temp_app, participant_id, {}, {}, HTML_WITH_SESSION)
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id)
        assert all(v == "NA" for v in loaded_ratings.values())
    
    def test_load_nonexistent_csv(self, temp_app):
        ratings, notes = temp_app.load_existing_ratings("999")
        assert ratings == {}
        assert notes == {}


class TestEdgeCases:
    """Test edge cases and potential issues."""
    
    def test_anatomical_modules_consistency(self, temp_app):
        participant_id = "004"
        anat_ratings = {
            "T1mask_run-1": "1",
            "Norm_run-1": "2",
            "SurfRecon_run-1": "1",
        }
        
        save_ratings_direct(temp_app, participant_id, anat_ratings, {}, HTML_WITH_SESSION)
        loaded, _ = temp_app.load_existing_ratings(participant_id)
        
        assert loaded["T1mask_run-1"] == "1"
        assert loaded["Norm_run-1"] == "2"
        assert loaded["SurfRecon_run-1"] == "1"
    
    def test_partial_ratings(self, temp_app):
        participant_id = "005"
        partial_ratings = {
            "Align_ses-01_run-1": "1",
            "Final_ses-01_run-1": "2",
        }
        
        save_ratings_direct(temp_app, participant_id, partial_ratings, {}, HTML_WITH_SESSION)
        loaded, _ = temp_app.load_existing_ratings(participant_id)
        
        assert loaded["Align_ses-01_run-1"] == "1"
        assert loaded["Final_ses-01_run-1"] == "2"
        assert loaded["BOLD_ses-01_run-1"] == "NA"
    
    def test_notes_without_ratings(self, temp_app):
        participant_id = "006"
        notes = {"Align_ses-01_run-1": "Note without rating"}
        
        save_ratings_direct(temp_app, participant_id, {}, notes, HTML_WITH_SESSION)
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id)
        
        assert loaded_notes["Align_ses-01_run-1"] == "Note without rating"
        assert loaded_ratings["Align_ses-01_run-1"] == "NA"


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_full_workflow_with_session(self, temp_app):
        participant_id = "007"
        
        # Parse and process
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        assert len(tasks) == 2
        
        _, modules = temp_app.process_html_modules(HTML_WITH_SESSION)
        all_ids = [m['id'] for group in modules for m in group]
        
        # Create ratings for specific modules
        ratings = {id_: "1" for id_ in all_ids if "Align" in id_ or "T1mask" in id_}
        
        # Save and load
        save_ratings_direct(temp_app, participant_id, ratings, {}, HTML_WITH_SESSION)
        loaded_ratings, _ = temp_app.load_existing_ratings(participant_id)
        
        for key in ratings:
            assert key in loaded_ratings
            assert loaded_ratings[key] == "1"
    
    def test_multiple_participants(self, temp_app):
        ratings_p1 = {"T1mask_run-1": "1", "Align_ses-01_run-1": "2"}
        ratings_p2 = {"T1mask_run-1": "2", "Align_ses-01_run-1": "1"}
        
        save_ratings_direct(temp_app, "p1", ratings_p1, {}, HTML_WITH_SESSION)
        save_ratings_direct(temp_app, "p2", ratings_p2, {}, HTML_WITH_SESSION)
        
        loaded_p1, _ = temp_app.load_existing_ratings("p1")
        loaded_p2, _ = temp_app.load_existing_ratings("p2")
        
        assert loaded_p1["T1mask_run-1"] == "1"
        assert loaded_p2["T1mask_run-1"] == "2"
        assert loaded_p1["Align_ses-01_run-1"] == "2"
        assert loaded_p2["Align_ses-01_run-1"] == "1"

class TestProcessHTMLModulesWithDivIds:

    def test_div_run_ids_correct(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_DIV_WITH_RUN)
        all_ids = [m['id'] for group in modules for m in group]

        assert 'SDC_ses-01_run-1' in all_ids
        assert 'Align_ses-01_run-1' in all_ids

        assert 'SDC_ses-01_run-2' in all_ids
        assert 'Align_ses-01_run-2' in all_ids
        assert 'CompCor_ses-01_run-2' in all_ids
        assert 'BOLD_ses-01_run-2' in all_ids

        assert 'CompCor_ses-01_run-1' not in all_ids
        assert 'BOLD_ses-01_run-1' not in all_ids

    def test_div_no_run_multitask_ids_correct(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_DIV_NO_RUN_MULTITASK)
        all_ids = [m['id'] for group in modules for m in group]

        for task in ('MID1', 'MID2', 'rest'):
            assert f'SDC_ses-01_task-{task}_run-1' in all_ids
            assert f'CompCor_ses-01_task-{task}_run-1' in all_ids

        sdc_ids = [id_ for id_ in all_ids if id_.startswith('SDC_ses-01')]
        assert len(sdc_ids) == 3

    def test_div_run_grouping(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_DIV_WITH_RUN)

        functional_groups = [g for g in modules if any('ses' in m['id'] for m in g)]
        assert len(functional_groups) == 2

        group_runs = sorted([g[0]['run'] for g in functional_groups])
        assert group_runs == [1, 2]

class TestMultiTaskWithBIDSRuns:
    """Two tasks in one session, both with BIDS run numbers.

    Regression guard: the task has to appear in the module id, or the two tasks
    collide on the same ids and the second one's ratings never reach its CSV.
    """

    def test_module_ids_are_unique(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_MULTITASK_WITH_RUNS)
        all_ids = [m['id'] for group in modules for m in group]
        duplicates = sorted({i for i in all_ids if all_ids.count(i) > 1})

        assert not duplicates, f"colliding ids: {duplicates}"

    def test_every_save_key_exists_in_frontend(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_MULTITASK_WITH_RUNS)
        all_ids = {m['id'] for group in modules for m in group}

        missing = [
            f"SDC{suffix}"
            for task_info in temp_app.parse_tasks_from_html(HTML_MULTITASK_WITH_RUNS)
            for suffix in task_info['suffixes']
            if f"SDC{suffix}" not in all_ids
        ]

        assert not missing, f"save_ratings looks up keys the frontend never created: {missing}"

    def test_both_tasks_keep_their_ratings(self, temp_app):
        participant_id = "900"
        _, modules = temp_app.process_html_modules(HTML_MULTITASK_WITH_RUNS)

        # Rate every module the frontend actually renders
        ratings = {m['id']: "1" for group in modules for m in group}
        rendered = {m['id'].split('_', 1)[0] for group in modules for m in group}

        save_ratings_direct(temp_app, participant_id, ratings, {}, HTML_MULTITASK_WITH_RUNS)

        for task in ("rest", "nback"):
            csv_file = temp_app.output_dir / f"sub-{participant_id}_ses-01_{task}.csv"
            assert csv_file.exists(), f"{task} CSV was not written"

            with csv_file.open(newline="", encoding="utf-8") as f:
                row = next(csv.DictReader(f))

            # Modules absent from the HTML get a column too, and it is legitimately NA
            na_cols = sorted(c for c, v in row.items()
                             if c.endswith("_r") and v == "NA" and c.rsplit("_", 2)[0] in rendered)
            assert not na_cols, f"{task} lost these ratings: {na_cols}"


class TestExtraEntitiesBetweenTaskAndRun:
    """Entities other than session/task/run in the heading and the div id."""

    def test_each_acquisition_becomes_its_own_unit(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_ACQ_BETWEEN_TASK_AND_RUN)

        assert [(t['name'], t['extras'], t['runs']) for t in tasks] == [
            ('rest', {'acq': 'seq'}, ['1', '2']),
            ('rest', {'acq': 'mb'}, ['1', '2']),
        ]

    def test_acquisitions_get_distinct_ids(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_ACQ_BETWEEN_TASK_AND_RUN)
        sdc_ids = [m['id'] for group in modules for m in group if m['id'].startswith('SDC_')]

        assert sdc_ids == ['SDC_ses-01_acq-seq_run-1', 'SDC_ses-01_acq-seq_run-2',
                           'SDC_ses-01_acq-mb_run-1', 'SDC_ses-01_acq-mb_run-2']

    def test_each_acquisition_gets_its_own_csv(self, temp_app):
        participant_id = "901"
        _, modules = temp_app.process_html_modules(HTML_ACQ_BETWEEN_TASK_AND_RUN)
        ratings = {m['id']: "1" for group in modules for m in group}

        save_ratings_direct(temp_app, participant_id, ratings, {}, HTML_ACQ_BETWEEN_TASK_AND_RUN)

        for acq in ("seq", "mb"):
            csv_file = temp_app.output_dir / f"sub-{participant_id}_ses-01_rest_acq-{acq}.csv"
            assert csv_file.exists(), f"acq-{acq} CSV was not written"

            with csv_file.open(newline="", encoding="utf-8") as f:
                row = next(csv.DictReader(f))

            assert [row["SDC_1_r"], row["SDC_2_r"]] == ["1", "1"]


class TestFieldmapGroups:
    """Fieldmap headings have no task and must not be mistaken for one."""

    def test_fieldmap_group_is_not_a_task(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_FIELDMAP_GROUPS)

        assert len(tasks) == 1
        assert (tasks[0]['name'], tasks[0]['session'], tasks[0]['runs']) == ('rest', '01', ['1'])

    def test_fieldmap_group_does_not_shift_run_numbers(self, temp_app):
        _, modules = temp_app.process_html_modules(HTML_FIELDMAP_GROUPS)
        all_ids = [m['id'] for group in modules for m in group]

        assert 'SDC_ses-01_run-1' in all_ids


class TestOlderReports:
    """Reports from fMRIPrep before 23.2 name the coregistration figure by its method."""

    @pytest.mark.parametrize("method", ["surface driven", "volume based"])
    def test_coregistration_is_rated(self, temp_app, method):
        html = f"""<h2 class="sub-report-group">Reports for: task <span class="bids-entity">rest</span>, run <span class="bids-entity">1</span>.</h2>
<h3 class="run-title">Alignment of functional and anatomical MRI data ({method})</h3>
<h3 class="run-title">BOLD Summary</h3>"""
        _, modules = temp_app.process_html_modules(html)
        assert [m['id'] for group in modules for m in group] == ['Align_run-1', 'BOLD_run-1', 'Final_run-1']


class TestRunNumbersFollowBIDS:
    """The run number in an id and in a CSV column is the BIDS run label."""

    def test_gapped_runs_keep_their_labels(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_GAPPED_RUNS)
        assert tasks[0]['runs'] == ['1', '3']

        _, modules = temp_app.process_html_modules(HTML_GAPPED_RUNS)
        sdc_ids = [m['id'] for group in modules for m in group if m['id'].startswith('SDC_')]
        assert sdc_ids == ['SDC_ses-01_run-1', 'SDC_ses-01_run-3']

    def test_gapped_runs_land_in_matching_csv_columns(self, temp_app):
        participant_id = "902"
        _, modules = temp_app.process_html_modules(HTML_GAPPED_RUNS)
        ratings = {m['id']: "1" for group in modules for m in group}

        save_ratings_direct(temp_app, participant_id, ratings, {}, HTML_GAPPED_RUNS)

        csv_file = temp_app.output_dir / f"sub-{participant_id}_ses-01_rest.csv"
        with csv_file.open(newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f))

        assert row["SDC_1_r"] == "1"
        assert row["SDC_3_r"] == "1"
        assert "SDC_2_r" not in row


class TestUnsupportedEntityWarning:
    """Raters are told up front when a task is split by an entity fmriqc prep cannot use."""

    def test_split_task_is_reported(self, temp_app, caplog):
        with caplog.at_level("WARNING"):
            temp_app._warn_unsupported_entities("001", temp_app.parse_tasks_from_html(HTML_ACQ_BETWEEN_TASK_AND_RUN))

        assert "acq-seq" in caplog.text and "acq-mb" in caplog.text
        assert "fmriqc prep" in caplog.text

    def test_plain_task_is_silent(self, temp_app, caplog):
        with caplog.at_level("WARNING"):
            temp_app._warn_unsupported_entities("001", temp_app.parse_tasks_from_html(HTML_WITH_SESSION))

        assert caplog.text == ""


class TestParticipantIdIsPreserved:
    """The subject label is a BIDS string: leading zeros stay, and `sub-` is a prefix."""

    def test_leading_zeros_survive_the_save(self, temp_app):
        participant_id = "0030"
        _, modules = temp_app.process_html_modules(HTML_WITH_SESSION)
        ratings = {m['id']: "1" for group in modules for m in group}

        save_ratings_direct(temp_app, participant_id, ratings, {}, HTML_WITH_SESSION)

        csv_file = temp_app.output_dir / f"sub-{participant_id}_ses-01_rest.csv"
        with csv_file.open(newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f))

        assert row["ID"] == "0030"

    def test_route_keeps_the_id_intact(self, temp_app):
        """URL -> template -> POST -> disk, for an id that both starts with 's' and is padded."""
        (temp_app.data_dir / "sub-0030.html").write_text(HTML_WITH_SESSION, encoding="utf-8")
        client = temp_app.app.test_client()

        page = client.get(f"/sub-0030?token={temp_app.gate.token}", follow_redirects=True).get_data(as_text=True)
        assert 'window.participantId = "0030"' in page

        _, modules = temp_app.process_html_modules(HTML_WITH_SESSION)
        ratings = {m['id']: "1" for group in modules for m in group}
        resp = client.post("/save_ratings", json={"id": "0030", "ratings": ratings, "notes": {}})

        assert resp.status_code == 200
        saved = json.loads((temp_app.output_dir / "sub-0030.json").read_text(encoding="utf-8"))
        assert saved["ratings"] == ratings

    def test_prefix_strip_does_not_eat_id_characters(self, temp_app):
        (temp_app.data_dir / "sub-s001.html").write_text(HTML_WITH_SESSION, encoding="utf-8")
        client = temp_app.app.test_client()

        page = client.get(f"/sub-s001?token={temp_app.gate.token}", follow_redirects=True).get_data(as_text=True)

        assert 'window.participantId = "s001"' in page


HTML_ANAT_ONLY = """
<nav class="navbar">Summary</nav>
<h2>Anatomical</h2>
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
<h3 class="run-title">Spatial normalization of the anatomical T1w reference</h3>
"""


class TestSaveRoute:
    """The real /save_ratings endpoint, not the save_ratings_direct mirror."""

    TOKEN = "t"

    @pytest.fixture
    def client_for(self, tmp_path):
        def make(html, pid="0030"):
            data_dir = tmp_path / "data"
            data_dir.mkdir(exist_ok=True)
            (data_dir / f"sub-{pid}.html").write_text(html, encoding="utf-8")
            app = FMRIPrepRatingApp(data_dir, tmp_path / "output", token=self.TOKEN)
            client = app.app.test_client()
            client.get(f"/sub-{pid}?token={self.TOKEN}")
            return app, client
        return make

    def test_anatomical_only_report_saves(self, client_for):
        app, client = client_for(HTML_ANAT_ONLY)
        resp = client.post("/save_ratings", json={"id": "0030", "ratings": {"T1mask_run-1": "1"}, "notes": {}})

        assert resp.status_code == 200
        assert json.loads((app.output_dir / "sub-0030.json").read_text())["ratings"] == {"T1mask_run-1": "1"}
        with (app.output_dir / "sub-0030.csv").open(newline="", encoding="utf-8") as f:
            assert next(csv.DictReader(f))["T1mask_1_r"] == "1"

    def test_sidecar_survives_a_failed_csv_export(self, client_for):
        app, client = client_for(HTML_WITH_SESSION)
        # A directory where the CSV should go makes the export fail, as a file locked by Excel would
        (app.output_dir / "sub-0030_ses-01_rest.csv").mkdir()
        ratings = {"SDC_ses-01_run-1": "1"}
        resp = client.post("/save_ratings", json={"id": "0030", "ratings": ratings, "notes": {}})

        assert resp.status_code == 500
        assert json.loads((app.output_dir / "sub-0030.json").read_text())["ratings"] == ratings


class TestGroupIdsStayUnique:
    """Groups that differ only by an entity some of them lack."""

    @staticmethod
    def suffixes(app, groups):
        return [g['suffix'] for g in app._label_groups(groups)]

    def test_entity_present_on_some_groups_only(self, temp_app):
        groups = [{'session': '01', 'task': 'rest', 'run': '1'},
                  {'session': '01', 'task': 'rest', 'acquisition': 'mb', 'run': '1'}]
        assert self.suffixes(temp_app, groups) == ['_ses-01_run-1', '_ses-01_acq-mb_run-1']

    def test_run_less_group_skips_a_used_run_label(self, temp_app):
        groups = [{'session': '01', 'task': 'rest', 'run': '1'},
                  {'session': '01', 'task': 'rest'}]
        assert self.suffixes(temp_app, groups) == ['_ses-01_run-1', '_ses-01_run-2']

    def test_shared_entity_is_still_left_out(self, temp_app):
        groups = [{'session': '01', 'task': 'rest', 'echo': '1', 'run': '1'},
                  {'session': '01', 'task': 'rest', 'echo': '1', 'run': '2'}]
        assert self.suffixes(temp_app, groups) == ['_ses-01_run-1', '_ses-01_run-2']


def nireports_page(nav, body):
    return (f'<!DOCTYPE html><html><head><title>Report</title></head><body>'
            f'<nav class="navbar fixed-top">{nav}</nav>{body}</body></html>')


ANAT_NAV = '<a href="#Summary">Summary</a><a href="#Anatomical">Anatomical</a>'
ANAT_BODY = """<div id="Summary"><h1>Summary</h1></div>
<div id="Anatomical"><h1>Anatomical</h1>
<h3 class="run-title">Brain mask and brain tissue segmentation of the T1w</h3>
<h3 class="run-title">Spatial normalization of the anatomical T1w reference</h3>
<h3 class="run-title">Surface reconstruction</h3></div>"""


def func_nav(session):
    return (f'<a id="navbarFunctional" href="#Functional">Functional</a>'
            f'<a href="#g{session}">Reports for: session <span>{session}</span>, task <span>rest</span>, '
            f'run <span>1</span>.</a>')


def func_body(session):
    return f"""<div id="Functional"><h1>Functional</h1>
<h2>Reports for: session <span>{session}</span>, task <span>rest</span>, run <span>1</span>.</h2>
<h3 class="run-title">Susceptibility distortion correction</h3>
<h3 class="run-title">BOLD Summary</h3></div>"""


class TestSplitReports:
    """fMRIPrep's split reports: anatomy apart past --aggregate-session-reports, or one full report per session."""

    TOKEN = "t"

    @staticmethod
    def write_split(data_dir):
        (data_dir / "sub-01_anat.html").write_text(nireports_page(ANAT_NAV, ANAT_BODY), encoding="utf-8")
        for session in ["1", "2"]:
            (data_dir / f"sub-01_ses-{session}_func.html").write_text(
                nireports_page(func_nav(session), func_body(session)), encoding="utf-8")

    @staticmethod
    def write_sessionwise(data_dir):
        for session in ["1", "2"]:
            (data_dir / f"sub-01_ses-{session}.html").write_text(
                nireports_page(ANAT_NAV + func_nav(session), ANAT_BODY + func_body(session)), encoding="utf-8")

    @pytest.fixture
    def client(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = FMRIPrepRatingApp(data_dir, tmp_path / "output", token=self.TOKEN)
        client = app.app.test_client()
        client.get(f"/01?token={self.TOKEN}")
        return app, client

    @staticmethod
    def page_modules(client):
        response = client.get("/01")
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        groups = json.loads(page.split("window.modulesByRunJson = ", 1)[1].split(";\n", 1)[0])
        return page, [[m["id"] for m in group] for group in groups]

    @staticmethod
    def read_csv(app, name):
        with (app.output_dir / name).open(newline="", encoding="utf-8") as f:
            return next(csv.DictReader(f))

    def test_anatomy_apart_from_each_session_is_rated_on_one_page(self, client):
        app, client = client
        self.write_split(app.data_dir)
        page, groups = self.page_modules(client)

        assert groups == [["T1mask_run-1", "Norm_run-1", "SurfRecon_run-1"],
                          ["SDC_ses-1_run-1", "BOLD_ses-1_run-1", "Final_ses-1_run-1"],
                          ["SDC_ses-2_run-1", "BOLD_ses-2_run-1", "Final_ses-2_run-1"]]
        # The later reports' fixed navbars would cover the first one's
        assert "navbarFunctional" not in page

        ratings = {"T1mask_run-1": "good", "SDC_ses-1_run-1": "bad", "SDC_ses-2_run-1": "other"}
        assert client.post("/save_ratings", json={"id": "01", "ratings": ratings, "notes": {}}).status_code == 200
        ses1, ses2 = self.read_csv(app, "sub-01_ses-1_rest.csv"), self.read_csv(app, "sub-01_ses-2_rest.csv")
        assert (ses1["T1mask_1_r"], ses1["SDC_1_r"]) == ("good", "bad")
        assert (ses2["T1mask_1_r"], ses2["SDC_1_r"]) == ("good", "other")

    def test_each_session_of_a_sessionwise_run_has_its_own_anatomy(self, client):
        app, client = client
        self.write_sessionwise(app.data_dir)
        page, groups = self.page_modules(client)

        assert groups == [["T1mask_ses-1_run-1", "Norm_ses-1_run-1", "SurfRecon_ses-1_run-1"],
                          ["SDC_ses-1_run-1", "BOLD_ses-1_run-1", "Final_ses-1_run-1"],
                          ["T1mask_ses-2_run-1", "Norm_ses-2_run-1", "SurfRecon_ses-2_run-1"],
                          ["SDC_ses-2_run-1", "BOLD_ses-2_run-1", "Final_ses-2_run-1"]]
        assert 'id="T1mask_ses-2_run-1"' in page

        ratings = {"T1mask_ses-1_run-1": "good", "T1mask_ses-2_run-1": "bad"}
        notes = {"T1mask_ses-2_run-1": "ghosting"}
        assert client.post("/save_ratings", json={"id": "01", "ratings": ratings, "notes": notes}).status_code == 200
        ses1, ses2 = self.read_csv(app, "sub-01_ses-1_rest.csv"), self.read_csv(app, "sub-01_ses-2_rest.csv")
        assert (ses1["T1mask_1_r"], ses1["T1mask_1_c"]) == ("good", "")
        assert (ses2["T1mask_1_r"], ses2["T1mask_1_c"]) == ("bad", "ghosting")

    def test_the_newer_reports_win_over_leftovers_of_an_older_run(self, client):
        app, client = client
        (app.data_dir / "sub-01.html").write_text(HTML_WITH_SESSION, encoding="utf-8")
        self.write_split(app.data_dir)
        os.utime(app.data_dir / "sub-01.html", (1, 1))
        assert self.page_modules(client)[1][1][0] == "SDC_ses-1_run-1"

        for path in app.data_dir.glob("sub-01_*.html"):
            os.utime(path, (1, 1))
        os.utime(app.data_dir / "sub-01.html", None)
        assert self.page_modules(client)[1][1][0] == "SDC_ses-01_run-1"
