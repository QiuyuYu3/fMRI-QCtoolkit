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

`fmriqc rating afni` runs AFNI's `open_apqc.py`, so that step also needs AFNI (see [Rating AFNI output](rating-afni.md)). The other commands do not use AFNI. Some AFNI modules put their own copies of Python packages such as numpy and pandas on the `PYTHONPATH`, which can break `fmriqc`; if that happens, see [Troubleshooting](troubleshooting.md#an-import-error-after-loading-the-afni-module).

## From the repository

The repository holds example data (`examples/example_data`) that the [Quick start](quickstart.md) uses; it is not part of the PyPI package. To use it, or to work on the code, clone the repository and install it in development mode:

```bash
git clone https://github.com/QiuyuYu3/fMRI-QCtoolkit.git
cd fMRI-QCtoolkit
pip install -e ".[dev]"
```

To build this handbook locally, install the documentation tools with `pip install -e ".[docs]"` and run `sphinx-build docs docs/_build/html`.
