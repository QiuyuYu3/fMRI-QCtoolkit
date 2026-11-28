# AOMIC-PIOP2 example

Outputs of `fmriqc prep` on a public dataset, for trying the dashboards on real ratings and metrics.

- `AFNI_workingmemory/df_final.csv`: APQC ratings and AFNI quality metrics for the working memory task.
- `fMRIPrep_restingstate/df_final.csv`: ratings of the fMRIPrep reports and MRIQC metrics for the resting-state run.

Open them with:

```
fmriqc dashboard afni \
    --data-file examples/aomic_piop2/AFNI_workingmemory/df_final.csv \
    --task workingmemory
```

```
fmriqc dashboard fmriprep \
    --data-file examples/aomic_piop2/fMRIPrep_restingstate/df_final.csv \
    --task restingstate
```

The imaging data are from AOMIC-PIOP2 (OpenNeuro ds002790, CC0): Snoek L, van der Miesen MM, Beemsterboer T, van der Leij A, Eigenhuis A, Scholte HS. The Amsterdam Open MRI Collection, a set of multimodal MRI datasets for individual difference analyses. Sci Data. 2021;8(1):85. doi:10.1038/s41597-021-00870-6
