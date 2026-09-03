# formal_protocol_v1.20 reduced-evaluation delta

## Status

- Protocol version: `formal_protocol_v1.20`
- Protocol date: 2026-09-03
- Verification status: `UNVERIFIED` until the bound Tree-Ring regression gate and 2-key smoke pass
- Base protocol: `formal_protocol_v1.19`
- Full Chinese authority: workspace-root `正式实验设置.md`

## User-approved removals

1. Do not save or evaluate the step-100 detector trajectory checkpoint. No detector trajectory checkpoints are retained.
2. Do not generate the forgery lambda or N six-panel detector-trajectory figures.
3. Do not run paired hypothesis tests, including McNemar or paired Wilcoxon tests, and do not apply Holm correction.
4. Do not score attacked outputs against non-target keys. Remove wrong-key acceptance, target rank and target top-1 metrics and tables.
5. Final target-key detection, ASR, image-quality metrics, FID, Wilson intervals, fixed tables, failure/ineligibility lists and cost records remain required.

## Unchanged settings

The 200-key matrix, 150-step budgets, scalar execution, methods, models, watermarks, target-key thresholds, zero-query attack rule, attack/evaluation isolation, resume semantics, retention of three qualitative visualization keys, Tree-Ring regression gate and 2-key smoke/full-run approval gates remain unchanged.

Historical v1.19 configs, protocol, smoke and results remain read-only and must not be resumed or combined with v1.20.
