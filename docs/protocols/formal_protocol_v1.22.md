# formal_protocol_v1.22 ephemeral-image-retention delta

- Protocol version: `formal_protocol_v1.22`
- Date: 2026-09-04
- Baseline: `formal_protocol_v1.21`

## Changes

1. The selected reference PNGs (30,000 in the 200-key formal run) are temporary working assets. After all 13,200 primary forgery outputs have completed, the runner verifies their unique identities and SHA-256 hashes, verifies every selected reference PNG against `reference_manifest.csv`, writes a deletion inventory, and deletes the selected reference PNGs before constructing E7 controls.
2. The manifests, selected-reference hashes, candidate decisions, deterministic seeds, reference latent cache, cleanup inventory and cleanup report remain persistent. Deleting PNGs does not alter any already-computed attack output or metric.
3. No reference, checkpoint, final-output, control or transformation PNG is permanently retained for `key_000`, `key_100`, `key_199`, or any other key. The full-run and smoke configurations therefore require `visualization_key_ids: []`.
4. Final images in `evaluation_spool/` remain temporary only until target-key detection, quality metrics and FID features are complete and their persistent rows and hashes are validated. The existing scoped spool cleanup then removes them.
5. Persistent deliverables are numeric results, manifests, hashes, runtime/cost records, result tables, aggregate statistical figures, logs, protocol/config snapshots, integrity checks and the run summary. A separate small-scale script may generate paper example images later; those images are outside this formal run.
6. Disk estimation must account for the phase overlap between all selected reference PNGs and primary outputs. The estimate must not add the full E7 spool to that overlap because selected reference PNGs are deleted before E7 begins.

All v1.21 scientific settings, fixed 150-step budgets, scalar execution, detector-free attack, experiment matrix, metrics, gates and statistical exclusions remain unchanged. Historical v1.21 configs, protocol, smoke and results are read-only and cannot be resumed or combined with v1.22.
