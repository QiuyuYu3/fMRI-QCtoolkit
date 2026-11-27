import glob
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

def fmriprep_reports(input_dir: Path, label: str):
    """A participant's report files in page order, each with its anatomy's session, and older leftovers."""
    input_dir = Path(input_dir)
    session_report = re.compile(rf'sub-{re.escape(label)}_ses-([A-Za-z0-9]+)(_func)?\.html')
    by_kind = {"func": [], "full": []}
    for path in input_dir.glob(f"sub-{glob.escape(label)}_ses-*.html"):
        match = session_report.fullmatch(path.name)
        if match:
            by_kind["func" if match.group(2) else "full"].append((match.group(1), path))
    whole = input_dir / f"sub-{label}.html"
    anat = input_dir / f"sub-{label}_anat.html"
    # One report; past --aggregate-session-reports, anatomy apart; sessionwise, a full report per session
    layouts = [
        [(whole, None)] if whole.exists() else [],
        ([(anat, None)] if anat.exists() else []) + [(path, None) for _, path in sorted(by_kind["func"])],
        [(path, session) for session, path in sorted(by_kind["full"])],
    ]
    layouts = [layout for layout in layouts if layout]
    if not layouts:
        return [], []
    newest = max(layouts, key=lambda layout: max(path.stat().st_mtime for path, _ in layout))
    return newest, [path for layout in layouts if layout is not newest for path, _ in layout]


def validate_fmriprep_subjects(input_dir: Path, subject_list: list):
    """Each found subject's report files, and the subjects without any."""
    missing_subjects = []
    found_files = []

    for subject_id in subject_list:
        reports, skipped = fmriprep_reports(input_dir, subject_id)
        if not reports:
            missing_subjects.append(subject_id)
            continue
        found_files.append([path for path, _ in reports])
        if skipped:
            typer.echo(f"Warning: sub-{subject_id} has reports from two fMRIPrep runs; rating the newer ones "
                       f"and skipping {', '.join(path.name for path in skipped)}")

    return found_files, missing_subjects


def validate_afni_subjects(input_dir: Path, subject_list: list, prefix: str, task: str = None):
    """Validate AFNI subjects and find their QC HTML files."""
    missing_subjects = []
    found_files = []

    for subject_id in subject_list:
        subject_clean = f"{prefix}{subject_id}"  # AFNI uses prefix + subject ID

        # AFNI pattern: search for *{task}*/QC_sub-XXX/index.html anywhere in input_dir
        base = f"*{task}*/**/" if task else "**/"
        # The session may be part of the subject ID given to afni_proc.py, as in QC_sub-01_ses-01
        found_paths = sorted({*input_dir.rglob(f"{base}QC_{subject_clean}/index.html"),
                              *input_dir.rglob(f"{base}QC_{subject_clean}_ses-*/index.html")})

        if found_paths:
            found_files.extend([str(p) for p in found_paths])
        else:
            missing_subjects.append(subject_id)

    return found_files, missing_subjects
