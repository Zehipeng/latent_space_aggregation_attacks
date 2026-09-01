# formal_protocol_v1.16 portable execution delta

## Status

- Protocol version: `formal_protocol_v1.16`
- Protocol date: 2026-09-01
- Verification status: `UNVERIFIED`
- Base protocol: `formal_protocol_v1.15`
- Full Chinese authority: workspace-root `正式实验设置.md`

## User-approved change

1. The experiment-output and result-package root is renamed from the Chinese directory `实验结果` to `outputs`.
2. The canonical AutoDL output root is `/root/autodl-tmp/outputs`.
3. `budget_selection_pilot`, `diagnostics`, `launch_logs`, `regression`, `smoke`, and all future formal run directories are children of `outputs/`.
4. Existing historical output directories are read-only records. They are not moved, overwritten, or merged with new runs.
5. Packaging must select the requested run beneath `/root/autodl-tmp/outputs` and must not package the project, model cache, datasets, or unrelated runs.

## Unchanged frozen settings

- `T_forgery_formal=1500`
- `T_removal_formal=1500`
- `beta_values=[1.0,1.5,2.0]`, with `main_beta=1.0`
- Three watermarks, same-model and cross-model settings, 200 formal keys
- Detector-free fixed-budget attack execution and physically separate offline evaluation
- All metrics, statistics, table/figure requirements, retention rules, and cleanup gates from v1.15

This delta preserves `formal_protocol_v1.15.md` and its checksum unchanged.
