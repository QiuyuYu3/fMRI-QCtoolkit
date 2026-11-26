# Installation

fMRI-QCtoolkit needs Python 3.11 or newer. Install it into a virtual environment so that its packages do not mix with others:

```bash
python -m venv qc-env
source qc-env/bin/activate          # on Windows: qc-env\Scripts\activate
pip install fmri-qctoolkit
```

This installs the `fmriqc` command. Check that it works with:

```bash
fmriqc --help
```

To update to the newest version later, activate the environment and run `pip install --upgrade fmri-qctoolkit`.

## On an HPC cluster

Load a Python module of version 3.11 or newer, then create and activate the environment as above. Activate it again in every new session before running `fmriqc`.

Only `fmriqc rating afni` needs AFNI. If `fmriqc` stops with an error after you load AFNI, see [Troubleshooting](troubleshooting.md#an-import-error-after-loading-the-afni-module).

## From the repository

The example data that the [Quick start](quickstart.md) uses is in the repository, not in the PyPI package. To try it, clone the repository and install from it:

```bash
git clone https://github.com/QiuyuYu3/fMRI-QCtoolkit.git
cd fMRI-QCtoolkit
pip install -e .
```
