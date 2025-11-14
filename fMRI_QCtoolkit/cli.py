import typer
from pathlib import Path
import subprocess

from .data.fmriprep_pipeline import FMRIPrepPipeline
from .data.afni_pipeline import AFNIPipeline
from .dashboard.fmriprep_app import FMRIPrepDashboard
from .dashboard.afni_app import AFNIDashboard
from .dashboard.fmriprep_rating_app import FMRIPrepRatingApp
from .utils.port_utils import find_free_port
from .utils.subject_utils import parse_subjects_input,validate_fmriprep_subjects,validate_afni_subjects

app = typer.Typer(help="MRI Quality Control Dashboard")

prep_app = typer.Typer(help="Data preparation")
dashboard_app = typer.Typer(help="Dashboard visualization")
rating_app = typer.Typer(help="Quality rating interface")

app.add_typer(prep_app, name="prep")
app.add_typer(dashboard_app, name="dashboard")
app.add_typer(rating_app, name="rating")

# -------------------
# Helper functions
# -------------------
def validate_dir_exists(path: Path, name: str):
    if not path.exists():
        typer.echo(f"{name} not found: {path}", err=True)
        raise typer.Exit(code=1)

def validate_file_exists(path: Path, name: str):
    if not path.exists():
        typer.echo(f"{name} not found: {path}", err=True)
        raise typer.Exit(code=1)

def ensure_output_dir(path: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        typer.echo(f"Cannot create output directory {path}: {e}", err=True)
        raise typer.Exit(code=1)

# ----------------------------
# Preparation Commands
# ----------------------------
@prep_app.command("afni")
def prep_afni(
    input_dir: Path = typer.Option(..., help="Input directory"),
    output_dir: Path = typer.Option(..., help="Output directory"),
    task: str = typer.Option(..., help="Task name. The program will automatically detect paths containing this field within the input directory."),
    prefix: str = typer.Option(..., help="Subject prefix, eg: sub-90=sub-(prefix)+90(ID)")
):
    validate_dir_exists(input_dir, "Input directory")
    ensure_output_dir(output_dir)

    typer.echo("Running AFNI data preparation...")
    pipeline = AFNIPipeline(
        input_dir=input_dir,
        task=task,
        prefix=prefix,
        output_dir=output_dir
    )
    pipeline.process()

    typer.echo("Data preparation complete!")
    typer.echo(f"Output files saved to: {output_dir}")
    typer.echo(f"To launch dashboard:\n qc dashboard afni --data-file {output_dir}/df_final.csv --lollipop-file {output_dir}/lollipop_chart_data.csv --task {task}")


@prep_app.command("fmriprep")
def prep_fmriprep(
    bold_file: Path = typer.Option(..., help="Path to group_bold.tsv"),
    rating_dir: Path = typer.Option(..., help="Directory with rating CSVs"),
    task: str = typer.Option(..., help="Task name, will be used to filter group.tsv"),
    output_dir: Path = typer.Option(..., help="Output directory")
):
    validate_file_exists(bold_file, "BOLD file")
    validate_dir_exists(rating_dir, "Rating directory")
    ensure_output_dir(output_dir)

    typer.echo("Running fMRIPrep data preparation...")
    pipeline = FMRIPrepPipeline(
        bold_file=bold_file,
        rating_dir=rating_dir,
        task=task,
        output_dir=output_dir,
    )
    pipeline.process()

    typer.echo("Data preparation complete!")
    typer.echo(f"Output files saved to: {output_dir}")
    typer.echo(f"To launch dashboard:\n qc dashboard fmriprep --data-file {output_dir}/df_final.csv --lollipop-file {output_dir}/lollipop_chart_data.csv --task {task}")

# ----------------------------
# Dashboard Commands
# ----------------------------
@dashboard_app.command("afni")
def dashboard_afni(
    data_file: Path = typer.Option(..., help="Pre-processed data file"),
    lollipop_file: Path = typer.Option(..., help="Lollipop chart file"),
    task: str = typer.Option(..., help="Task name"),
    host: str = typer.Option("127.0.0.1", help="Host address"),
    debug: bool = typer.Option(False, help="Run in debug mode")
):
    validate_file_exists(data_file, "Data file")
    validate_file_exists(lollipop_file, "Lollipop file")

    # Auto-detect available port
    try:
        port = find_free_port(start=5000, end=5500, delay=0.2)
        typer.echo(f"Found available port: {port}")
    except RuntimeError as e:
        typer.echo(f"Port allocation failed: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Starting AFNI dashboard at http://{host}:{port}")
    
    pipeline = AFNIPipeline.from_saved_data(
        data_file=data_file,
        lollipop_file=lollipop_file,
        task=task,
    )
    dashboard = AFNIDashboard(pipeline, task=task)
    # webbrowser.open(f"http://{host}:{port}")
    dashboard.run(host=host, port=port, debug=debug)


@dashboard_app.command("fmriprep")
def dashboard_fmriprep(
    data_file: Path = typer.Option(..., help="Pre-processed data file"),
    lollipop_file: Path = typer.Option(..., help="Lollipop chart file"),
    task: str = typer.Option(..., help="Task name"),
    host: str = typer.Option("127.0.0.1", help="Host address"),
    debug: bool = typer.Option(False, help="Run in debug mode")
):
    validate_file_exists(data_file, "Data file")
    validate_file_exists(lollipop_file, "Lollipop file")

    # Auto-detect available port
    try:
        port = find_free_port(start=5000, end=5500, delay=0.2)
        typer.echo(f"Found available port: {port}")
    except RuntimeError as e:
        typer.echo(f"Port allocation failed: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Starting fMRIPrep dashboard at http://{host}:{port}")
    
    pipeline = FMRIPrepPipeline.from_saved_data(
        data_file=data_file,
        lollipop_file=lollipop_file,
        task=task,
    )
    dashboard = FMRIPrepDashboard(pipeline, task=task)
    # webbrowser.open(f"http://{host}:{port}")
    dashboard.run(host=host, port=port, debug=debug)

# ----------------------------
# Rating Commands
# ----------------------------
@rating_app.command("fmriprep") 
def rating_fmriprep(
    input_dir: Path = typer.Option(..., help="Directory containing fMRIPrep HTML reports"),
    output_dir: Path = typer.Option(..., help="Directory to save rating CSV files"),
    subjects: str = typer.Option(..., help="Subjects to rate (comma/space separated or path to text file)"),
):
    validate_dir_exists(input_dir, "Input directory")
    ensure_output_dir(output_dir)
    
    subject_list = parse_subjects_input(subjects)
    if not subject_list:
        typer.echo("No subjects found to rate", err=True)
        raise typer.Exit(code=1)

    found_files, missing_subjects = validate_fmriprep_subjects(input_dir, subject_list)
    
    if missing_subjects:
        typer.echo(f"Warning: HTML files not found for subjects: {', '.join(map(str, missing_subjects))}")
        if not found_files:
            typer.echo("No HTML files found for any subjects", err=True)
            raise typer.Exit(code=1)

        subject_list = [s for s in subject_list if s not in missing_subjects]
        typer.echo(f"Proceeding with {len(subject_list)} subjects: {', '.join(subject_list[:5])}{'...' if len(subject_list) > 5 else ''}")
    
    typer.echo("Starting fMRIPrep rating interface...")
    typer.echo("Rate each subject's quality control report")
    typer.echo("Ratings will be saved automatically as CSV files")
    typer.echo("If the program cannot detect the session and run number, both will default to 1.")
    typer.echo("Browser tabs will open for each subject")
    
    rating_app_instance = FMRIPrepRatingApp(
        data_dir=input_dir,
        output_dir=output_dir,
        subjects=subject_list
    )
    
    try:
        rating_app_instance.run_app_and_open_browsers()
    except KeyboardInterrupt:
        typer.echo("\n Rating session ended")
    except Exception as e:
        typer.echo(f"Error running rating app: {e}", err=True)
        raise typer.Exit(code=1)


@rating_app.command("afni")
def rating_afni(
    input_dir: Path = typer.Option(..., help="AFNI derivatives' root directory"),
    subjects: str = typer.Option(..., help="Subjects to rate (comma/space separated or path to text file)"),
    task: str = typer.Option(..., help="Task name. The program will automatically detect paths containing this field within the input directory."),
    prefix: str = typer.Option(..., help="Prefix for AFNI subjects, e.g., 'sub-'"),
    afni_path: str = typer.Option("/apps/eb/AFNI/24.3.06-foss-2023a/bin", help="Path to AFNI binaries (will be added to $PATH)"),
):
    validate_dir_exists(input_dir, "Input directory")

    subject_list = parse_subjects_input(subjects)
    if not subject_list:
        typer.echo("No subjects found to rate", err=True)
        raise typer.Exit(code=1)

    html_files, missing_subjects = validate_afni_subjects(input_dir, subject_list, prefix=prefix, task=task)
    
    if missing_subjects:
        typer.echo(f"Warning: HTML files not found for subjects: {', '.join(map(str, missing_subjects))}")
    if not html_files:
        typer.echo("No AFNI QC HTML files found", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(html_files)} AFNI QC files")

    cmd = f"""
    export PATH="{afni_path}:$PATH"
    open_apqc.py -infiles {' '.join(html_files)}
    """
    subprocess.run(cmd, shell=True, check=False)


if __name__ == "__main__":
    app()