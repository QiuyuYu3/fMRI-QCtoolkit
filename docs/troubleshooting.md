# Troubleshooting

## The page says "Access denied"

The link's token belongs to one run of the command. Every start prints a new link, so use the one printed most recently. A rating page that cannot save says the same: the server was restarted, so open the new link.

## The link does not open on an HPC cluster

The browser on your own computer cannot reach the cluster. Open the link in Firefox on the cluster's remote desktop instead, as described in [Opening the pages](opening-pages.md#on-an-hpc-cluster).

## "Port allocation failed"

The dashboard looks for a free port between 5000 and 5500. Stop old dashboards you no longer need (Ctrl+C in their terminals) and start again.

## `open_apqc.py not found`

`fmriqc rating afni` needs AFNI's `open_apqc.py`. Load the AFNI module, or give the folder that holds it with `--afni-path`. See [Rating AFNI output](rating-afni.md#before-you-start).

## An import error after loading the AFNI module

Some AFNI modules bring their own Python packages, which clash with `fmriqc`. A typical message is `No module named 'numpy.core._multiarray_umath'`. Load AFNI only for `fmriqc rating afni`, and run `fmriqc prep` and `fmriqc dashboard` in a new terminal without it. If rating still fails, ask your cluster's support for an AFNI module that matches your Python version.

## No reports or JSON files are found

`--task` must be a part of the path between `--input-dir` and each participant's QC folder, and `--prefix` must match the folder names (`sub-` for `QC_sub-001`). Check one participant's path against the [folder layout](rating-afni.md#folder-layout).

## "More than one QC directory matching task"

`fmriqc prep afni` makes one row per participant. If a participant has a match in several sessions, narrow `--task` to one session, for example `ses-01/rest`.

## No ratings match the MRIQC rows

`fmriqc prep fmriprep` matches ratings to MRIQC's rows by participant, session and run, and warns when nothing matches. Check that `--task` is written as in the file names, and that the session labels agree: a rating file without a session counts as session 1, as does an MRIQC row without one.

## The dashboard stops with "Config error"

The settings file has a mistake, and the message names the entry and the problem. Fix the file by hand, or move it away so that the dashboard starts from the defaults. Files from version 1.x no longer work; write a new one with `fmriqc config` (see [Config file](config.md)).

## Save fails in the Settings tab

The dashboard could not write to the folder of the settings file. Use **Download config** to keep the settings, and next time start the dashboard with `--config` pointing to a file in a folder you can write to.
