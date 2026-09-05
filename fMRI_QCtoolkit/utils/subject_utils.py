from pathlib import Path
import typer
import re

def parse_subjects_input(subjects_input: str) -> list:
    """Parse subjects from string input (comma/space separated) or file path."""
    subjects_path = Path(subjects_input)
    
    # Check if input is a file path
    if subjects_path.exists() and subjects_path.is_file():
        typer.echo(f"Reading subjects from file: {subjects_path}")
        try:
            content = subjects_path.read_text().strip()
        except Exception as e:
            typer.echo(f"Error reading subjects file: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        # Treat as direct string input
        content = subjects_input
    
    # Use regex to split by comma and/or whitespace
    # \s+ matches one or more whitespace characters
    # , matches comma
    subjects = re.split(r'[,\s]+', content.strip())
    subjects = [s for s in subjects if s]  # Remove empty strings
    
    # Clean up subject IDs (remove 'sub-' prefix if present)
    subjects = [str(s).strip().removeprefix('sub-') for s in subjects]
    
    typer.echo(f"Found {len(subjects)} subjects: {', '.join(subjects[:5])}{'...' if len(subjects) > 5 else ''}")
    return subjects

def validate_fmriprep_subjects(input_dir: Path, subject_list: list):
    """Validate fMRIPrep subjects and find their HTML files."""
    missing_subjects = []
    found_files = []

    for subject_id in subject_list:
        subject_clean = f"sub-{subject_id}"  # fMRIPrep HTML pattern
        html_file = input_dir / f"{subject_clean}.html"

        if html_file.exists():
            found_files.append(html_file)
        else:
            missing_subjects.append(subject_id)

    return found_files, missing_subjects


def validate_afni_subjects(input_dir: Path, subject_list: list, prefix: str, task: str = None):
    """Validate AFNI subjects and find their QC HTML files."""
    missing_subjects = []
    found_files = []

    for subject_id in subject_list:
        subject_clean = f"{prefix}{subject_id}"  # AFNI uses prefix + subject ID

        # AFNI pattern: search for *{task}*/QC_sub-XXX/index.html anywhere in input_dir
        if task:
            qc_pattern = f"*{task}*/**/QC_{subject_clean}/index.html"
        else:
            qc_pattern = f"**/QC_{subject_clean}/index.html"

        found_paths = list(input_dir.rglob(qc_pattern))

        if found_paths:
            found_files.extend([str(p) for p in found_paths])
        else:
            missing_subjects.append(subject_id)

    return found_files, missing_subjects
