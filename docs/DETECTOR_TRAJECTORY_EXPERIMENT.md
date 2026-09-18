# Single-Img versus FR-LA detector trajectories v1

## Material Passport

Scope: independent diagnostic experiment; source: user-approved settings and committed implementation.
Status: code workflow, not experimental evidence. Excluded from formal_protocol_v1.22 statistics.

40 preregistered keys key_000–key_039; SD2 target / SD1.4 proxy VAE; RingID and Gaussian Shading.
Both tasks use 150 updates, LR 0.02, lambda 10000. Record 0,10,...,150 (16 points).
Single-Img is the existing Jain implementation: first-reference latent for forgery; constant mean-image latent for removal.
FR-LA uses five-reference FP32 arithmetic mean for forgery; mean-shift removal with five references,
five nonpaired clean priors and beta=1.5. Removal source is first accepted reference and belongs to the aggregate.
Methods share source, key, seed, update rule and budget. References are the first 25 accepted among
the same 64 preregistered candidates, not reselected based on attack results.

320 attack units / 5120 checkpoint detections. Preparation may be expensive: 80 watermark-key groups,
each with 25 accepted reference images. No early stop or detector queries during attack.
PNG quantization is identical for both methods. Every 10 updates, atomically save PNG/hash and resume state.
Resume validates commit/config/assets/input identities; corrupted state fails instead of silently restarting.
Evaluation starts in a separate process only after all checkpoints of the task are verified.

Results: `outputs/detector_trajectory/<run_id>/evaluation/{forgery,removal}/` contains
`per_key_trajectory.csv`, `trajectory_summary.csv`, `report.json`. Finalize verifies both tasks.
Initial detection eligibility is retained only as per-key metadata, never as a summary filter.
Both metrics use the arithmetic mean over all fixed 40 keys at each step. Missing, duplicate,
non-finite or out-of-range scores stop summary generation; no failed key is silently dropped.
No median, quartiles, bootstrap or interval bands. `center` is the mean; `sample_n=total_n=40`.
Mean p-value is a descriptive detector score, not a combined hypothesis-test p-value.
All per-key data remain available. This aggregation is user-approved, not attributed to Müller code.
Do not call bit accuracy bitrate. Produce four independent figures: forgery RingID p-value,
forgery Gaussian Shading bit accuracy, removal RingID p-value, removal Gaussian Shading bit accuracy.
Each figure has two method lines, 16 checkpoints and no interval bands.
Detector thresholds: RingID p<=0.05; Gaussian Shading bit accuracy>=0.6484375.

Use `python scripts/run_detector_trajectories.py --dry-run` to inspect the contract without assets.
Use `--phase preflight` to verify lock hashes and actually load proxy VAE, SD2 and both key adapters offline.
Preflight requires clean tracked source, CUDA and >=10 GiB free disk (minimum guard, not measured peak estimate).
It never downloads assets. Missing assets must be prepared separately; do not disable offline during attacks.
`--phase run` runs preflight, shared preparation, forgery attack/evaluate, removal attack/evaluate, finalize.
Separate task launchers: `scripts/run_detector_trajectory_forgery.sh` and `scripts/run_detector_trajectory_removal.sh`.
Reuse the same run-id when launching tasks separately, then run `--phase finalize`.
No automatic deletion. Download numeric results/logs/identity first; retain checkpoints until integrity review.
GPU execution and scientific equivalence remain unverified until AutoDL reports successful execution.
