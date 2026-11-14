# E1 statistical reliability analysis

This analysis is post-hoc and does not generate or attack images. It consumes
the persistent per-key CSV produced by a completed formal run.

## Frozen analysis choices

- ASR denominator: eligible samples only.
- ASR interval: two-sided 95% Wilson interval.
- Continuous summaries: mean, sample standard deviation and two-sided 95%
  percentile-bootstrap interval of the mean.
- Condition bootstrap: 2,000 replicates.
- Paired comparisons: 5,000 paired bootstrap replicates, paired by `key_id`.
- Master seed: 205.
- Detector acceptance margin:
  - Tree-Ring/RingID: `threshold - p_value`;
  - Gaussian Shading: `bit_accuracy - threshold`.
- Task margin: acceptance margin for forgery, negative acceptance margin for
  removal. Positive values therefore support task success for every watermark.
- No p-values or multiple-testing claims are emitted. Paired effects report the
  mean difference, its bootstrap interval and standardized paired effect `dz`.

The preregistered paired comparisons are:

1. every attack condition versus its exact L2-matched Gaussian-noise control;
2. proposed `N=1` versus Jain `N=1` at the same fidelity weight;
3. proposed main setting (`lambda=20000`, removal `beta=1.5`) versus RGB simple
   averaging with the same reference count.

## Existing formal results

```powershell
python scripts/analysis/run_e1_statistical_reliability.py `
  --input "formal_forgery_v1p22=<forgery-run>/evaluation/final_per_key_metrics.csv" `
  --input "formal_removal_v1p22=<removal-run>/evaluation/final_per_key_metrics.csv" `
  --output-dir analysis_outputs/e1_existing_v1 `
  --bootstrap-replicates 2000 `
  --paired-bootstrap-replicates 5000 `
  --confidence 0.95 `
  --seed 205
```

## Outputs

- `e1_condition_reliability.csv`: condition-level ASR and continuous-metric
  uncertainty.
- `e1_detection_signal_per_key.csv`: normalized detector scores and margins for
  distribution plots and residual-signal analysis.
- `e1_paired_comparisons.csv`: preregistered key-paired effect estimates.
- `e1_analysis_manifest.json`: input hashes, row counts, settings and output
  hashes.

When the 200-key reviewer single-reference run finishes, rerun the same command
with its `evaluation/final_per_key_metrics.csv` as a third labeled input. The
source label is part of every grouping key, so identical condition IDs from
different runs cannot be merged accidentally.
