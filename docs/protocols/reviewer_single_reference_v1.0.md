# Reviewer single-reference protocol v1.0

This additive protocol answers the reviewer question about the practical value of
latent averaging when only one watermarked reference is available. It does not
modify or replace `formal_protocol_v1.22` or `limited_access_v1.0`.

## Frozen design

- Target/proxy settings: SD1.4/SD1.4 and SD2/SD1.4.
- Watermarks: Tree-Ring, RingID and Gaussian Shading.
- Tasks: removal and forgery.
- Watermarked references: exactly one in every condition.
- Clean-prior sweep: `N_clean = {1, 5, 25}` at `lambda=20000`, `beta=1.5`.
- Fidelity sweep: `lambda = {10000, 20000, 50000}` at `N_clean=5`, `beta=1.5`.
- Removal-strength sweep: `beta = {1.0, 1.5, 2.0}` at `N_clean=5`,
  `lambda=20000`; forgery remains fixed at `beta=1.5`.
- Shared base settings are de-duplicated. This yields five forgery and seven
  removal conditions per model/watermark pair: 72 conditions total.
- Smoke: two keys and 144 outputs. Formal: 200 keys and 14,400 outputs.
- Optimization: 150 steps, learning rate 0.02, scalar batch size one, no online
  detection and no early stopping.

For a single watermarked latent `z_w` and the first `N_clean` non-paired clean
latents, define `d = z_w - mean(z_clean)`. Removal targets
`z_w - beta*d`; forgery targets `z_source + 1.5*d`.

## Evaluation and separation

The attack worker never loads a detector. A separate evaluation process computes
ASR, LPIPS, SSIM, PSNR, FID, optimization time, initial/final detector scores and
threshold margin. Results are emitted both per unit and as `N_clean`, `lambda`,
and removal-`beta` reporting tables.

The same 25 clean-prior images are ordered once per key and nested across the
`N_clean` sweep. The clean forgery source is fixed separately. Each model,
watermark, key, condition, configuration hash and Git commit is recorded.

## Gates and retention

The Tree-Ring regression must pass on the exact commit and asset lock. The full
run is blocked until the complete two-key smoke passes and its ETA/disk report is
reviewed. Starting the 200-key run requires a second invocation with explicit
`--approve-full-run`. Checkpoints are saved every 50 steps; completed units are
hash-checked and skipped on restart. Images are deleted only after persistent
numeric outputs and checksums are verified; manifests, reports, tables and logs
are retained.
