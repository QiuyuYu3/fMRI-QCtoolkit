import subprocess
import sys
from importlib.metadata import version as package_version
from pathlib import Path

HERE = Path(__file__).parent

project = "fMRI-QCtoolkit"
author = "Qiuyu Yu"
copyright = "Qiuyu Yu"
release = package_version("fmri_qctoolkit")
version = release

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build", "_generated"]

html_theme = "furo"
html_title = f"fMRI-QCtoolkit {release}"
html_theme_options = {
    "source_repository": "https://github.com/QiuyuYu3/fMRI-QCtoolkit",
    "source_branch": "main",
    "source_directory": "docs/",
}

# The command reference is written from the installed CLI, so it always matches the code
(HERE / "_generated").mkdir(exist_ok=True)
subprocess.run([sys.executable, "-m", "typer", "fMRI_QCtoolkit.cli", "utils", "docs", "--name", "fmriqc",
                "--output", str(HERE / "_generated" / "cli.md")], check=True)
