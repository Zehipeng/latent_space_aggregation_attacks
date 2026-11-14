# E2/E4 server runbook

This run is independent of the active single-reference run. Use a new release
directory and a new run ID. Do not modify either completed v1.22 baseline run.

## 1. Variables

```bash
PROJECT=/data/zengzhipeng/code/releases/latent_space_aggregation_attacks_<commit>
ASSETS=/data/zengzhipeng/assets/assets.lock.json
LEGACY=/data/zengzhipeng/code/legacy/jain_multiref_latent_experiment_legacy_eb7ec9b_clean_20260908
RUN_ID=reviewer_selection_mechanism_v1p0_a6000_r1
REGRESSION=/project/zengzhipeng/outputs/regression/${RUN_ID}_tree_ring.json
FORMAL=/project/zengzhipeng/outputs/reviewer_selection_mechanism/$RUN_ID
```

Use the Python interpreter from the already validated experiment environment.

## 2. Offline asset preflight

```bash
cd "$PROJECT"
"$PY" scripts/run_reviewer_selection_mechanism.py \
  --config configs/server/reviewer_selection_mechanism_formal_200key_lab.yaml \
  --assets-lock "$ASSETS" \
  --offline \
  --preflight-only
```

Expected: `PREFLIGHT_PASSED`, 48 conditions, 96 smoke outputs and 9,600
planned formal outputs.

## 3. Exact-commit GPU regression

```bash
mkdir -p "$(dirname "$REGRESSION")"
"$PY" scripts/validate_tree_ring.py \
  --config configs/server/reviewer_selection_mechanism_formal_200key_lab.yaml \
  --assets-lock "$ASSETS" \
  --legacy-project "$LEGACY" \
  --output "$REGRESSION" \
  --offline
```

Expected: `status: PASSED` and zero image, target, preprocessing and ten-step
attack differences within the recorded tolerances.

## 4. Two-key smoke

Run inside a dedicated tmux session. The command exits after smoke and writes a
runtime/disk estimate; it does not automatically start the formal run.

```bash
tmux new -s e2e4_smoke
cd "$PROJECT"
"$PY" scripts/run_reviewer_selection_mechanism.py \
  --config configs/server/reviewer_selection_mechanism_formal_200key_lab.yaml \
  --smoke-config configs/server/reviewer_selection_mechanism_smoke_2key_lab.yaml \
  --assets-lock "$ASSETS" \
  --run-id "$RUN_ID" \
  --tree-ring-regression-report "$REGRESSION" \
  --offline \
  --smoke-only
```

Detach with `Ctrl-b`, then `d`. Progress is always available at:

```bash
watch -n 30 "cat /project/zengzhipeng/outputs/smoke/reviewer_selection_mechanism/${RUN_ID}_smoke/progress.json 2>/dev/null || echo waiting"
```

Exit `watch` with `Ctrl-c`.

## 5. Formal approval

Only after smoke checksums and `runtime_estimate.json` are reviewed:

```bash
tmux new -s e2e4_formal
cd "$PROJECT"
"$PY" scripts/run_reviewer_selection_mechanism.py \
  --config configs/server/reviewer_selection_mechanism_formal_200key_lab.yaml \
  --smoke-config configs/server/reviewer_selection_mechanism_smoke_2key_lab.yaml \
  --assets-lock "$ASSETS" \
  --run-id "$RUN_ID" \
  --tree-ring-regression-report "$REGRESSION" \
  --offline \
  --approve-full-run
```

The formal progress file is `$FORMAL/progress.json`.

## 6. Reuse the ordered-verified v1.22 baseline

After formal E2/E4 evaluation completes, point the following command at the two
immutable v1.22 run directories. This verifies their checksum manifests and
performs paired-by-key analysis; it does not launch GPU attacks.

```bash
"$PY" scripts/analysis/merge_e2_ordered_baseline.py \
  --e2-run "$FORMAL" \
  --forgery-run /absolute/path/to/formal_forgery_v1p22_200key \
  --removal-run /absolute/path/to/formal_removal_v1p22_200key
```

E2 is analysis-complete only when
`evaluation/e2_baseline_provenance.json` reports `COMPLETE`.
