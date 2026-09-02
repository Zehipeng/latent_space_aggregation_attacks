# Cleanup candidates

This is a review list only. No tracked file in this list is deleted automatically.

## Safe generated files (not tracked)

- `.pytest_cache/`
- every `__pycache__/` directory
- every `*.pyc` file

These are recreated by Python/pytest and are already ignored by Git.

## Tracked files that can be deleted after explicit approval

### Inactive five-line placeholders

All files below only call `guarded_entry(...)`; they contain no experiment
implementation and no active code imports them:

- `scripts/archive/placeholders/run_forgery.py`
- `scripts/archive/placeholders/run_removal.py`
- `scripts/archive/placeholders/run_jain_forgery.py`
- `scripts/archive/placeholders/run_jain_removal.py`
- `scripts/archive/placeholders/run_simple_averaging.py`
- `scripts/archive/placeholders/run_distortion_removal.py`
- `scripts/archive/placeholders/evaluate_final.py`
- `scripts/archive/placeholders/evaluate_detector_trajectories.py`
- `scripts/archive/placeholders/build_tables_and_figures.py`

Deleting these would not affect the v1.17 formal call chain.

### Empty legacy package

- `src/latent_space_aggregation_attacks/methods/proposed/__init__.py`

The active optimizer and target definitions now live at `attack.py` and
`latent_targets.py`. No source or test imports the old package.

### Superseded standalone ETA checker

- `scripts/operations/estimate_runtime.py`

The formal orchestrator already creates the authoritative GPU smoke-derived
`runtime_estimate.json`. Keep this standalone checker only if manually supplied
stage-measurement JSON remains useful.

## Keep for reproducibility

Do not delete these merely to make the tree shorter:

- `docs/protocols/archive/` and its checksum files;
- `configs/archive/`;
- `scripts/archive/p0/` and `src/.../archive/p0_runtime.py`;
- `docs/archive/autodl_stage_c_v1p15.md`.

They preserve the provenance of v1.15/v1.16 and historical P0 runs. They may be
moved to a separate archival repository later, but deleting them would weaken
reproducibility and historical traceability.
