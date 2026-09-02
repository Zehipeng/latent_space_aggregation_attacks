# formal_protocol_v1.17 compute-budget and validated-batching delta

## Status

- Protocol version: `formal_protocol_v1.17`
- Protocol date: 2026-09-02
- Verification status: `UNVERIFIED` until the bound GPU equivalence gate and 2-key smoke pass
- Base protocol: `formal_protocol_v1.16`
- Full Chinese authority: workspace-root `正式实验设置.md`

## User-approved changes

1. `T_forgery_formal` and `T_removal_formal` are both changed from 1500 to 150 steps.
2. Detector trajectories use steps `0,100,150`; the final frozen step is always retained.
3. Independent iterative units are optimized in batches of four with per-sample mean losses summed across the batch, preserving each sample's scalar gradient definition.
4. Final and trajectory DDIM inversions are batched up to eight images. A physical checkpoint shared by the lambda and N trajectory views is inverted once and its score is fanned out to both registered rows.
5. Reference images are encoded in batches of eight and exact FP32 reference latents are cached by model/watermark/key/reference hashes for reuse across conditions.
6. Formal execution requires a GPU equivalence report bound to protocol version, full Git SHA, resolved config hash, assets-lock hash, device/runtime metadata, and batch settings.

## Equivalence gate

- Compare attack batch size 1 against batch size 4 using identical inputs, targets, lambdas, update count and learning rate.
- Compare scalar inversion against batch size 8 for every registered watermark adapter.
- Record maximum absolute tensor differences and detector-score differences.
- Require identical accept/reject decisions for all gate cases; threshold-near discrepancies fail closed.
- The gate validates computational equivalence within recorded floating-point tolerances; it does not claim byte-identical PNG output across CUDA kernels.

## Unchanged settings

All v1.16 experiment matrices, methods, keys, assets, detector thresholds, zero-query attack rule, physical attack/evaluation separation, metrics, statistical tests, tables, figures, retention rules, and smoke/full-run gates remain unchanged unless explicitly listed above.

Historical v1.16 configs, protocol snapshot, runs, and results remain read-only and must not be resumed as v1.17.
