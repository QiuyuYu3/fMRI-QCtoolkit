# Preparing the table

`fmriqc prep` collects the ratings and the quantitative metrics of all participants into one table, `df_final.csv`, which the dashboard reads. It keeps every numeric metric it finds, so you can add any of them to the dashboard later without running `fmriqc prep` again.

## AFNI

```bash
fmriqc prep afni \
    --input-dir /PATH/AFNI_derivatives \
    --task ses-01/kidvid \
    --prefix sub- \
    --output-dir /PATH/QC
```

`--input-dir`
: The folder that holds all participants' AFNI output.

`--task`
: A part of the path between `--input-dir` and each participant's QC folder, usually the task name. Each row is one participant, so if a participant matches in more than one place (for example `ses-01/rest_output` and `ses-02/rest_output`), the command stops and lists them; narrow `--task` to one session, such as `ses-01/rest`.

`--prefix`
: What comes before the ID in the folder names, usually `sub-`. It is removed from the IDs in the table.

`--output-dir`
: The folder for `df_final.csv`. It is created if needed.

The command reads `QC_<ID>/extra_info/out.ss_review.<ID>.json` of every participant. This file holds the quantitative summary of `afni_proc.py` (the `qsumm` block of the APQC report) and the APQC ratings. In `df_final.csv`:

- Every numeric field becomes a column. A field with several values, such as one per run or one per stimulus class, becomes one column per value, numbered `_1`, `_2` and so on.
- Text fields, such as the AFNI version or the names of the output datasets, are left out.
- Field names have spaces replaced by `_`, and the main metrics get short names:

| Column | Field in the review file |
|---|---|
| `runs` | num runs found |
| `TRs_total_raw` | TRs total (uncensored) |
| `TRs_removed` | TRs removed (per run) |
| `cens_mot` | average censored motion |
| `cens_displace` | max censored displacement |
| `DF_frac` | final DF fraction |
| `TSNR` | TSNR average |
| `cens_frac` | censor fraction |
| `GCOR` | global correlation (GCOR) |
| `frac_TRs_cens_1`, `_2`, ... | fraction TRs censored, per stimulus class |
| `flip_guess` | flip guess: 0 for NO_FLIP, 1 otherwise |

- The ratings are the columns ending in `_rating` (`vorig_rating`, `ve2a_rating`, ..., `FINAL_rating`), one per APQC block.

## fMRIPrep

```bash
fmriqc prep fmriprep \
    --bold-file /PATH/mriqc/group_bold.tsv \
    --rating-dir /PATH/ratings \
    --task rest \
    --output-dir /PATH/QC
```

`--bold-file`
: MRIQC's group table of functional metrics, `group_bold.tsv`.

`--rating-dir`
: The folder that `fmriqc rating fmriprep` saved the ratings to (its `--output-dir`).

`--task`
: The task to keep, as it appears in the file names (`task-rest` gives `rest`).

`--output-dir`
: The folder for `df_final.csv`. It is created if needed.

The command takes the rows of `group_bold.tsv` for `--task`, reads the participant, session and run from each row's `bids_name` (session 1 or run 1 when the name has none), and keeps every numeric metric that MRIQC computed; MRIQC's documentation describes them in [Image quality metrics](https://mriqc.readthedocs.io/en/latest/iqms/bold.html). It then reads the rating files `sub-<ID>_ses-<session>_<task>.csv` in `--rating-dir` and matches them to the metrics by participant, session and run.

Runs that have metrics but no ratings, or ratings but no metrics, are kept, with the missing part left empty. The terminal says how many runs matched; if none did, it warns and shows the labels on each side, which usually means the session or run labels differ between the ratings and MRIQC.

The rating columns are `T1mask`, `Norm`, `SurfRecon`, `SDC`, `Align`, `CompCor`, `Variance`, `BOLD`, `Corr` and `Final` (see [What you rate](rating-fmriprep.md#what-you-rate)).

## The table, df_final.csv

`df_final.csv` has one row per participant (AFNI) or per run (fMRIPrep):

- `ID`, and for fMRIPrep `session` and `run`, which identify the row;
- the numeric metrics, at full precision;
- the ratings, each `good`, `bad` or `other`, or empty when not rated.

The dashboard shows a chosen set of these columns (see [Settings tab](settings.md)); downloads from the dashboard keep all of them.

`fmriqc prep` is meant for users who prefer not to write code. If your data are arranged differently, you can write your own script that produces a `df_final.csv` with the same columns and open it with `fmriqc dashboard`.
