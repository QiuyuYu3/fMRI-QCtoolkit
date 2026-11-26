from importlib.metadata import version as package_version

project = "fMRI-QCtoolkit"
author = "Qiuyu Yu"
copyright = "Qiuyu Yu"
release = package_version("fmri_qctoolkit")
version = release

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build"]

html_theme = "furo"
html_title = f"fMRI-QCtoolkit {release}"
html_theme_options = {
    "source_repository": "https://github.com/QiuyuYu3/fMRI-QCtoolkit",
    "source_branch": "main",
    "source_directory": "docs/",
}
