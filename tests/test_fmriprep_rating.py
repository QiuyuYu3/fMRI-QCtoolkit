"""
Unit tests for fmriprep_rating_app module.
Focus on field matching across parse_tasks, process_html, load_ratings, and save_ratings.
"""

import pytest
import tempfile
import csv
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
    "Align_run-1": "2",
    "BOLD_run-1": "1",
    "Final_run-1": "2",
    "Align_run-2": "1",
    "BOLD_run-2": "2",
    "Final_run-2": "1",
    "Align_run-3": "1",
    "BOLD_run-3": "1",
    "Final_run-3": "2",
}

MOCK_NOTES_NO_SESSION = {
    "Align_run-1": "First run looks good",
    "BOLD_run-3": "Last run has motion",
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
    """Direct save method for testing (bypasses Flask)."""
    tasks = app.parse_tasks_from_html(html_content)
    
    if not tasks:
        raise ValueError("No tasks found")
    
    tasks_by_session = {}
    for task_info in tasks:
        session = task_info['session']
        if session not in tasks_by_session:
            tasks_by_session[session] = []
        tasks_by_session[session].append(task_info)
    
    all_combined_data = {}
    
    for session in sorted(tasks_by_session.keys(), key=lambda x: (x is None, x or '')):
        session_tasks = tasks_by_session[session]
        session_run_counter = 1
        
        for task_info in session_tasks:
            task_name = task_info['name']
            task_runs = task_info['runs']
            
            row_data = {"ID": participant_id}
            
            for mod in app.COMMON_MODULES:
                frontend_key = f"{mod}_run-1"
                row_data[f"{mod}_1_r"] = ratings.get(frontend_key, "NA")
                row_data[f"{mod}_1_c"] = notes.get(frontend_key, "")
            
            for local_run in range(1, task_runs + 1):
                global_run = session_run_counter + local_run - 1
                
                for mod in app.FUNCTIONAL_MODULES:
                    if session is None:
                        frontend_key = f"{mod}_run-{global_run}"
                    else:
                        frontend_key = f"{mod}_ses-{session}_run-{global_run}"
                    
                    row_data[f"{mod}_{local_run}_r"] = ratings.get(frontend_key, "NA")
                    row_data[f"{mod}_{local_run}_c"] = notes.get(frontend_key, "")
                
                if session is None:
                    final_key = f"Final_run-{global_run}"
                else:
                    final_key = f"Final_ses-{session}_run-{global_run}"
                
                row_data[f"Final_{local_run}_r"] = ratings.get(final_key, "NA")
                row_data[f"Final_{local_run}_c"] = notes.get(final_key, "")
            
            if session is None:
                csv_file = app.output_dir / f"sub-{participant_id}_{task_name}.csv"
                csv_prefix = task_name
            else:
                csv_file = app.output_dir / f"sub-{participant_id}_ses-{session}_{task_name}.csv"
                csv_prefix = f"ses-{session}_{task_name}"
            
            with csv_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(row_data.keys()))
                writer.writeheader()
                writer.writerow(row_data)
            
            for key, value in row_data.items():
                if key != "ID":
                    all_combined_data[f"{csv_prefix}_{key}"] = value
            
            session_run_counter += task_runs
    
    combined_csv = app.output_dir / f"sub-{participant_id}.csv"
    combined_row = {"ID": participant_id, **all_combined_data}
    
    with combined_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(combined_row.keys()))
        writer.writeheader()
        writer.writerow(combined_row)


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
        assert tasks[0] == {'name': 'rest', 'runs': 2, 'session': '01'}
        assert tasks[1] == {'name': 'motor', 'runs': 1, 'session': '02'}
    
    def test_no_session_with_runs(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_NO_SESSION)
        assert len(tasks) == 2
        assert tasks[0] == {'name': 'localizer', 'runs': 2, 'session': None}
        assert tasks[1] == {'name': 'rest', 'runs': 1, 'session': None}
    
    def test_mixed_sessions(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_MIXED)
        assert len(tasks) == 2
        assert tasks[0] == {'name': 'rest', 'runs': 1, 'session': '01'}
        assert tasks[1] == {'name': 'localizer', 'runs': 1, 'session': None}
    
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
            'Align_run-1', 'Align_run-2', 'Align_run-3',
            'Final_run-1', 'Final_run-2', 'Final_run-3'
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
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        verify_ratings_match(loaded_ratings, MOCK_RATINGS_WITH_SESSION)
        verify_notes_match(loaded_notes, MOCK_NOTES_WITH_SESSION)
    
    def test_roundtrip_no_session(self, temp_app):
        participant_id = "002"
        
        save_ratings_direct(temp_app, participant_id, MOCK_RATINGS_NO_SESSION,
                          MOCK_NOTES_NO_SESSION, HTML_NO_SESSION)
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id, HTML_NO_SESSION)
        verify_ratings_match(loaded_ratings, MOCK_RATINGS_NO_SESSION)
        verify_notes_match(loaded_notes, MOCK_NOTES_NO_SESSION)
    
    def test_empty_ratings(self, temp_app):
        participant_id = "003"
        save_ratings_direct(temp_app, participant_id, {}, {}, HTML_WITH_SESSION)
        
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        assert all(v == "NA" for v in loaded_ratings.values())
    
    def test_load_nonexistent_csv(self, temp_app):
        ratings, notes = temp_app.load_existing_ratings("999", HTML_WITH_SESSION)
        assert ratings == {}
        assert notes == {}


class TestCSVColumnMapping:
    """Test _map_csv_column_to_frontend_id function."""
    
    def test_format_session_task_module(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        
        test_cases = [
            ("ses-01_rest_Align_1_r", "Align_ses-01_run-1"),
            ("ses-01_rest_Align_2_r", "Align_ses-01_run-2"),
            ("ses-02_motor_Align_1_r", "Align_ses-02_run-1"),
            ("ses-01_rest_Final_1_r", "Final_ses-01_run-1"),
            ("ses-01_rest_BOLD_1_c", "BOLD_ses-01_run-1"),
        ]
        
        for csv_col, expected_id in test_cases:
            result = temp_app._map_csv_column_to_frontend_id(csv_col, tasks)
            assert result == expected_id, f"Failed: {csv_col} -> expected {expected_id}, got {result}"
    
    def test_format_task_module_no_session(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_NO_SESSION)
        
        test_cases = [
            ("localizer_Align_1_r", "Align_run-1"),
            ("localizer_Align_2_r", "Align_run-2"),
            ("rest_Align_1_r", "Align_run-3"),
            ("localizer_Final_1_c", "Final_run-1"),
            ("rest_BOLD_1_r", "BOLD_run-3"),
        ]
        
        for csv_col, expected_id in test_cases:
            result = temp_app._map_csv_column_to_frontend_id(csv_col, tasks)
            assert result == expected_id, f"Failed: {csv_col} -> expected {expected_id}, got {result}"
    
    def test_format_legacy(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        
        test_cases = [
            ("Align_1_r", "Align_ses-01_run-1"),
            ("BOLD_2_r", "BOLD_ses-01_run-2"),
            ("Final_1_c", "Final_ses-01_run-1"),
        ]
        
        for csv_col, expected_id in test_cases:
            result = temp_app._map_csv_column_to_frontend_id(csv_col, tasks)
            assert result == expected_id, f"Failed: {csv_col} -> expected {expected_id}, got {result}"
    
    def test_anatomical_modules_always_run1(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        
        test_cases = [
            ("ses-01_rest_T1mask_1_r", "T1mask_run-1"),
            ("ses-01_rest_Norm_1_c", "Norm_run-1"),
            ("T1mask_1_r", "T1mask_run-1"),
        ]
        
        for csv_col, expected_id in test_cases:
            result = temp_app._map_csv_column_to_frontend_id(csv_col, tasks)
            assert result == expected_id
    
    def test_invalid_column_returns_none(self, temp_app):
        tasks = temp_app.parse_tasks_from_html(HTML_WITH_SESSION)
        
        for col in ["InvalidModule_1_r", "completely_wrong_format"]:
            result = temp_app._map_csv_column_to_frontend_id(col, tasks)
            assert result is None, f"Expected None for invalid column: {col}"


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
        loaded, _ = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        
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
        loaded, _ = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        
        assert loaded["Align_ses-01_run-1"] == "1"
        assert loaded["Final_ses-01_run-1"] == "2"
        assert loaded["BOLD_ses-01_run-1"] == "NA"
    
    def test_notes_without_ratings(self, temp_app):
        participant_id = "006"
        notes = {"Align_ses-01_run-1": "Note without rating"}
        
        save_ratings_direct(temp_app, participant_id, {}, notes, HTML_WITH_SESSION)
        loaded_ratings, loaded_notes = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        
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
        loaded_ratings, _ = temp_app.load_existing_ratings(participant_id, HTML_WITH_SESSION)
        
        for key in ratings:
            assert key in loaded_ratings
            assert loaded_ratings[key] == "1"
    
    def test_multiple_participants(self, temp_app):
        ratings_p1 = {"T1mask_run-1": "1", "Align_ses-01_run-1": "2"}
        ratings_p2 = {"T1mask_run-1": "2", "Align_ses-01_run-1": "1"}
        
        save_ratings_direct(temp_app, "p1", ratings_p1, {}, HTML_WITH_SESSION)
        save_ratings_direct(temp_app, "p2", ratings_p2, {}, HTML_WITH_SESSION)
        
        loaded_p1, _ = temp_app.load_existing_ratings("p1", HTML_WITH_SESSION)
        loaded_p2, _ = temp_app.load_existing_ratings("p2", HTML_WITH_SESSION)
        
        assert loaded_p1["T1mask_run-1"] == "1"
        assert loaded_p2["T1mask_run-1"] == "2"
        assert loaded_p1["Align_ses-01_run-1"] == "2"
        assert loaded_p2["Align_ses-01_run-1"] == "1"