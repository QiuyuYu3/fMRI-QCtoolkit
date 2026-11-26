# Default thresholds

These are the thresholds the dashboard starts with. Change them in the [Settings tab](settings.md); the [Config file](config.md) page shows where they are stored.

In the tables, a run that meets the Bad rule is bad, one that meets the Good rule is good, and the rest get the level in the last column.

## AFNI

The AFNI thresholds follow the warning and exclusion levels of Reynolds et al. (2023): a value at the warning level is rated other, and one at the exclusion level is rated bad.

| Metric | Column | Good | Bad | Otherwise |
|---|---|---|---|---|
| Censor Fraction | `cens_frac` | < 0.15 | ≥ 0.2 | other |
| Average Censored Motion | `cens_mot` | < 0.1 | ≥ 0.15 | other |
| Max Censored Displacement | `cens_displace` | < 6 | ≥ 8 | other |
| TSNR Average | `TSNR` | > 150 | | other |
| Final DF Fraction | `DF_frac` | > 0.7 | ≤ 0.6 | other |
| Flip Guess | `flip_guess` | | ≠ 0 | good |
| GCOR | `GCOR` | < 0.15 | ≥ 0.2 | other |
| Fraction TRs Censored | `frac_TRs_cens_*`, one per stimulus class | | ≥ 0.2 | good |

## fMRIPrep

The fMRIPrep dashboard rates two motion metrics from MRIQC, with cut-offs adapted from the AFNI ones:

| Metric | Column | Good | Bad | Otherwise |
|---|---|---|---|---|
| % of FDs above threshold | `fd_perc` | ≤ 15 | > 20 | other |
| Average FD | `fd_mean` | < 0.2 | ≥ 0.3 | other |

The sidebar also shows these MRIQC metrics without thresholds, so they can be filtered but are not rated: TSNR Average (`tsnr`), GCOR (`gcor`), DVARS (`dvars_nstd`), Ghost to Signal Ratio X and Y (`gsr_x`, `gsr_y`), AFNI's Outlier Ratio (`aor`) and AFNI's Quality Index (`aqi`). MRIQC's [Image quality metrics](https://mriqc.readthedocs.io/en/latest/iqms/bold.html) page defines each of them.

## Reference

Reynolds, R. C., Taylor, P. A., & Glen, D. R. (2023). Quality control practices in FMRI analysis: Philosophy, methods and examples using AFNI. *Frontiers in Neuroscience*, 16, 1073800. <https://doi.org/10.3389/fnins.2022.1073800>
