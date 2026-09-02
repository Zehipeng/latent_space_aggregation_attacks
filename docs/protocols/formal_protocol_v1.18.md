# formal_protocol_v1.18 scalar-execution delta

## Status

- Protocol version: `formal_protocol_v1.18`
- Protocol date: 2026-09-02
- Verification status: `UNVERIFIED` until the bound Tree-Ring regression gate and 2-key smoke pass
- Base protocol: `formal_protocol_v1.17`
- Full Chinese authority: workspace-root `正式实验设置.md`

## User-approved changes

1. The v1.17 GPU equivalence gate failed for FP16 attack batch 4 and inversion batch 8. The failed report remains read-only evidence and must not be converted to `PASSED` by relaxing tolerances.
2. Formal attack optimization is scalar: `attack_batch_size=1`.
3. Final and trajectory DDIM inversion is scalar: `inversion_batch_size=1`.
4. Reference VAE encoding is scalar: `reference_encode_batch_size=1`.
5. The batch-equivalence report is no longer a formal prerequisite because no numerical batching is enabled. The SHA/config/assets-bound Tree-Ring regression gate remains mandatory.
6. Deduplicating an identical physical trajectory checkpoint remains permitted: the checkpoint is inverted once and the same scalar result is registered in each applicable table view. This is reuse of one result, not batched computation.

## Unchanged settings

The 150-step budgets, experiment matrices, methods, keys, assets, detector thresholds, zero-query attack rule, attack/evaluation isolation, metrics, statistics, tables, figures, retention rules, resume semantics, and smoke/full-run approval gates remain unchanged.

Historical v1.17 configs, protocol snapshot, failed batch-equivalence report, runs, and results remain read-only and must not be resumed as v1.18.
