# Your own tables

`fmriqc prep custom` and `fmriqc dashboard custom` open ratings and metrics from any software, for any kind of scan, as long as they are in a table. A table with only ratings, or only metrics, works too.

## Preparing the table

```bash
fmriqc prep custom \
    --input /PATH/my_ratings.csv \
    --input /PATH/my_metrics.tsv \
    --output-dir /PATH/QC
```

`--input`
: A `.csv` or `.tsv` file. Repeat it to give several files.

`--output-dir`
: The folder for `df_final.csv`. It is created if needed.

Each file has one row per participant, session or run, with these columns:

- `ID`, the participant. A leading `sub-` is removed, so `sub-001` and `001` are the same participant.
- `session` and `run`, if the data have them. A leading `ses-` or `run-` is removed, and runs are numbers, so `run-01` and `1` are the same run.
- Any other columns, with your ratings and metrics.

The files are matched on the ID, session and run columns they share. A file with only `ID` (one row per participant) gives its values to each of that participant's runs. Rows found in only one file are kept, with the other files' columns left empty. The terminal says how many rows matched, and warns when none did.

Two rows of one file with the same ID, session and run, or one column name used twice, in one file or across files, stop the command with a message that names them.

## How the columns are read

Each column is sorted by its values. Empty cells do not count.

| Values | In the dashboard |
|---|---|
| Only `good`, `other` and `bad`, in any case | A rating: a filter list and a row in the ratings heatmap |
| Only numbers | A metric: a slider, thresholds in the Settings tab, a row in the metrics heatmap once it has thresholds, and the lollipop chart |
| Anything else | Shown in the table and the downloads only |

The terminal lists the columns of each kind. For a column shown in the table only, it lists the values that kept it there, such as `pass (10 rows), fail (5 rows)`.

To filter on a column of ratings, change its values to `good`, `other` or `bad` (at least `good` and `bad`) and run `fmriqc prep custom` again. One misspelt value, such as `goood`, keeps the whole column in the table only.

Scores such as 1 to 5 are read as numbers. To rate them good or bad, give them thresholds in the [Settings tab](settings.md).

## Opening the dashboard

```bash
fmriqc dashboard custom \
    --data-file /PATH/QC/df_final.csv
```

`--task` is optional here; when given, it names the downloaded files. `--config` works as for the other dashboards (see [Config file](config.md)); the settings are saved as `custom_config.json` beside `df_final.csv`.

When the dashboard opens, every metric is in the sidebar without thresholds, so no run is hidden, and the other columns are in the table. In the [Settings tab](settings.md), remove the metrics you do not need and set thresholds for the others. **Use defaults** brings back every metric without thresholds.

The rest of the dashboard works as described in [Dashboard](dashboard.md). A part of the Plots tab with nothing to show is left out: the metrics heatmap appears once a metric has thresholds.
