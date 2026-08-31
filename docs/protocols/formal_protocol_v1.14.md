# Formal protocol v1.14 snapshot

## Status

- Protocol version: `formal_protocol_v1.14`
- Date: 2026-08-31
- Verification status: UNVERIFIED protocol; this file is not an experiment result.
- Base snapshot: `formal_protocol_v1.13.md`, incorporated except where superseded below.

## Authoritative v1.14 amendments

1. Forgery and removal P0 are separate experiments with separate scripts, resolved configs, smoke gates, run IDs, result directories, CSV files, ASR curves and summaries. Data from the two tasks must never be written to the same P0 result table.
2. Forgery P0 uses the first 50 preregistered pilot keys, all three watermarks, the cross-model setting, Proposed, `N=5`, `lambda=10000`, online detection every 100 steps, early stopping at first success and `T_forgery_max=3000`. Its smoke contains 6 units and its full P0 contains 150 units.
3. Removal P0 uses the same 50-key/three-watermark/cross-model structure in a separate run. Until the beta diagnostic is reviewed, it retains `beta=1.0` and `T_removal_max=15000`. Its smoke contains 6 units and its full P0 contains 150 units.
4. Add a separate removal parameter diagnostic over `pilot_key_000` through `pilot_key_009`, all three watermarks, the cross-model setting, Proposed, `N=5`, `lambda=10000`, `beta=1.5` and a fixed 3000-step budget. It performs no online detector queries and no early stopping. It persists no checkpoint PNGs.
5. The diagnostic reports only final ASR, l2, linf, LPIPS-Alex, SSIM, PSNR and threshold-normalized optimization progress percent. It keeps final attack images for integrity and offline evaluation. It does not generate checkpoint images, detector trajectories, ASR-by-step curves or FID.
6. Threshold-normalized removal progress is `100*(p_final-p_initial)/(0.05-p_initial)` for Tree-Ring/RingID and `100*(a_initial-a_final)/(a_initial-a_threshold)` for Gaussian Shading. Zero percent is the initial accepted sample; 100 percent reaches the formal rejection boundary. Values are not capped.
7. The 10-key diagnostic is development evidence only. It must not be merged into P0 budget curves, formal ASR, confidence intervals or paper tables. Formal `beta=1.0` remains unchanged until the user reviews the diagnostic and explicitly approves another protocol upgrade.
8. Task budgets are selected and frozen separately as `T_forgery_formal` and `T_removal_formal`. Within each task, every iterative method, watermark and model setting shares the same frozen budget. Method-specific budget selection within a task remains prohibited.
9. P0 storage remains reference-PNG-free. Each task-specific 2-key smoke saves 6 endpoint PNGs and one task-specific curve; each task-specific 50-key P0 saves 150 endpoint PNGs and one task-specific curve.
10. The full Chinese authority is the workspace-root `正式实验设置.md` at version v1.14. This repository snapshot is the portable execution contract and preserves v1.13 unchanged.
