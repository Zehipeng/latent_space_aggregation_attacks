# formal_protocol_v1.19 removal-main-beta delta

## Status

- Protocol version: `formal_protocol_v1.19`
- Protocol date: 2026-09-02
- Verification status: `UNVERIFIED` until the bound Tree-Ring regression gate and 2-key smoke pass
- Base protocol: `formal_protocol_v1.18`
- Full Chinese authority: workspace-root `正式实验设置.md`

## User-approved change

1. The Proposed removal main setting changes from `beta=1.0` to `beta=1.5`.
2. E2 Proposed removal uses `beta=1.5`.
3. E3 removal lambda sensitivity fixes `beta=1.5`.
4. E4 removal reference-count sensitivity fixes `beta=1.5`.
5. E5 keeps `beta_values=[1.0,1.5,2.0]`; its `beta=1.5` condition reuses the E2 output.
6. Jain removal, Simple Averaging, all forgery conditions, and the mathematical removal target are unchanged.

## Unchanged settings

The 150-step budgets, scalar execution, experiment sizes, keys, assets, detector thresholds, zero-query attack rule, attack/evaluation isolation, metrics, statistics, tables, figures, retention rules, resume semantics, and smoke/full-run approval gates remain unchanged.

Historical v1.18 configs, protocol snapshot, runs, and results remain read-only and must not be resumed or merged as v1.19.
