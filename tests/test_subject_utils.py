from pathlib import Path
import pytest
import numpy as np

from fMRI_QCtoolkit.utils.subject_utils import (
    parse_subjects_input,
    validate_fmriprep_subjects,
    validate_afni_subjects,
)

@pytest.fixture()
def random_subject_ids():
    """Generate random subject IDs for testing"""
    np.random.seed(42)
    return [str(np.random.randint(1000, 9999)) for _ in range(10)]


# regular input
def test_parse_subjects_input_from_string_list():
    subjects = parse_subjects_input("sub-1013, 1026  1030")
    assert subjects == ["1013", "1026", "1030"]


def test_parse_subjects_input_from_string_list_random(random_subject_ids):
    """Test parsing with random subject IDs"""
    # Create comma-separated string
    input_str = ", ".join([f"sub-{sid}" for sid in random_subject_ids[:5]])
    subjects = parse_subjects_input(input_str)
    
    # Should extract numeric IDs without sub- prefix
    expected = random_subject_ids[:5]
    assert subjects == expected


def test_parse_subjects_input_strips_prefix_not_characters():
    """`sub-` is a prefix, not a character set: an ID starting with s/u/b must survive."""
    subjects = parse_subjects_input("s001, sub-0030, bus-12, sub-sub-1, u7")
    assert subjects == ["s001", "0030", "bus-12", "sub-1", "u7"]


def test_parse_subjects_input_keeps_leading_zeros():
    subjects = parse_subjects_input("sub-0030, 090, sub-001")
    assert subjects == ["0030", "090", "001"]


def test_parse_subjects_input_from_file(tmp_path: Path):
    content = "sub-1001,sub-1002, 1003"
    file_path = tmp_path / "subs.txt"
    file_path.write_text(content)
    subjects = parse_subjects_input(str(file_path))
    assert subjects == ["1001", "1002", "1003"]


def test_parse_subjects_input_from_file_random(tmp_path: Path, random_subject_ids):
    """Test parsing from file with random subject IDs"""
    content = ", ".join([f"sub-{sid}" for sid in random_subject_ids[:3]])
    file_path = tmp_path / "subs.txt"
    file_path.write_text(content)
    subjects = parse_subjects_input(str(file_path))
    assert subjects == random_subject_ids[:3]

# fmriprep pipeline, prepare html files
def test_validate_fmriprep_subjects(tmp_path: Path):
    existing = ["sub-2001.html", "sub-2003.html"]
    for name in existing:
        (tmp_path / name).write_text("<html></html>")
    found, missing = validate_fmriprep_subjects(tmp_path, ["2001", "2002", "2003"]) 
    assert len(found) == 2
    assert set(missing) == {"2002"}


def test_validate_fmriprep_subjects_random(tmp_path: Path, random_subject_ids):
    """Test fMRIPrep validation with random subject IDs"""
    existing_subjects = random_subject_ids[:5]
    missing_subjects = random_subject_ids[5:8]
    
    for sid in existing_subjects:
        (tmp_path / f"sub-{sid}.html").write_text("<html></html>")
    
    found, missing = validate_fmriprep_subjects(tmp_path, existing_subjects + missing_subjects)
    
    assert len(found) == len(existing_subjects)
    assert set(missing) == set(missing_subjects)

# afni pipeline, prepare QC_*html files
def test_validate_afni_subjects(tmp_path: Path):
    # directory layout: any path containing task string, then QC_{prefix+id}/index.html
    task = "rest"
    prefix = "sub-"
    root = tmp_path / f"project_{task}" / "group" / "somewhere"
    (root / "QC_sub-3001").mkdir(parents=True)
    (root / "QC_sub-3001" / "index.html").write_text("<html></html>")

    found, missing = validate_afni_subjects(tmp_path, ["3001", "3002"], prefix=prefix, task=task)
    assert any(Path(p).parts[-2:] == ("QC_sub-3001", "index.html") for p in found)
    assert "3002" in missing


def test_validate_afni_subjects_random(tmp_path: Path, random_subject_ids):
    """Test AFNI validation with random subject IDs"""
    task = "rest"
    prefix = "sub-"
    root = tmp_path / f"project_{task}" / "group" / "somewhere"
    
    # Create QC directories for some random subjects
    existing_subjects = random_subject_ids[:3]
    missing_subjects = random_subject_ids[3:6]
    
    for sid in existing_subjects:
        qc_dir = root / f"QC_{prefix}{sid}"
        qc_dir.mkdir(parents=True)
        (qc_dir / "index.html").write_text("<html></html>")
    
    found, missing = validate_afni_subjects(
        tmp_path, 
        existing_subjects + missing_subjects, 
        prefix=prefix, 
        task=task
    )
    
    assert len(found) == len(existing_subjects)
    assert set(missing) == set(missing_subjects)


