# Reviewer reference-selection and mechanism protocol v1.0

## Status and scope

This protocol is preregistered before implementation and execution. It addresses
reference-selection bias and supplies reusable evidence for centroid and removal-
direction analysis. It does not modify a running `formal_protocol_v1.22` or
`reviewer_single_reference_v1.0` run, and it does not repeat the clean-reference,
fidelity-weight or removal-strength sweeps.

E2 and E4 share preparation artifacts but produce separate tables and claims:

- E2 asks whether the detector-validated, ordered reference construction biases
  attack performance.
- E4 asks whether centroid/direction quantities and detector response show stable
  associations under key and clean-set controls.

## Common frozen setting

- Keys: 200 formal keys; complete two-key smoke first.
- Models: SD1.4 target/SD1.4 proxy and SD2 target/SD1.4 proxy.
- Watermarks: Tree-Ring, RingID and Gaussian Shading.
- Tasks: forgery and removal.
- Method: proposed latent-aggregation attack only.
- Watermarked reference count: `N_w=25`.
- Clean reference count for the attacked removal direction: `N_c=25`.
- Fidelity weight: `lambda=10000`.
- Removal strength: `beta=1.5`.
- Optimization: 150 steps, learning rate 0.02, scalar batch size one.
- No detector queries, detector imports or early stopping in the attack worker.
- Final metrics: ASR with Wilson interval, LPIPS, SSIM, PSNR, FID, time,
  initial/final detector score and task-oriented threshold margin.
- Fixed assets, prompt universe, clean-image universe and watermark thresholds
  are inherited from formal v1.22 and must pass the exact-commit regression gate.

## Full candidate bank

Preparation deterministically regenerates all 64 preregistered candidates for
every `(model, watermark, key)` tuple, rather than stopping after 25 accepted
images. This yields 76,800 generated candidate images before temporary cleanup.
Each row records prompt hash, generation seed, canonical image hash, detector
score, accepted flag and candidate index.

Candidate detection is an offline experimental-construction step. The attack
worker receives only the frozen selected-image hashes and never receives the
detector, candidate scores or acceptance flags.

## E2 reference-selection strategies

The original v1.22 ordered-verified baseline is reused by immutable manifest and
result hash; it is not attacked again in the formal E2 run.

After E2 evaluation, `scripts/analysis/merge_e2_ordered_baseline.py` verifies
the `checksums.sha256` files of the completed v1.22 forgery and removal runs,
selects only proposed-method `N=25`, `lambda=10000`, 150-step rows (and
`beta=1.5` for removal), and creates paired-by-key comparisons. This post-run
merge is mandatory before E2 is considered analysis-complete; it performs no
new GPU attack.

New strategies use the same 64-image bank:

1. `random_verified_25_seed17`;
2. `random_verified_25_seed29`;
3. `random_verified_25_seed43`;
4. `unfiltered_ordered_25` (candidate indices 0--24, without detector filtering).

Random strategies uniformly sample 25 images without replacement from every
tuple's complete accepted set. If fewer than 25 accepted images exist, that tuple
is declared ineligible before attack; it is never silently replaced or resampled.
The random seed is derived from the strategy seed, model, watermark and key.

Formal new-attack scale: `4 strategies x 2 models x 3 watermarks x 2 tasks x
200 keys = 9,600 outputs`. All strategies for a key reuse identical attack source,
clean references, optimizer and evaluation settings. Analyses are paired by key.

Candidate-pool sensitivity is reported descriptively from the complete bank as
the number/proportion of tuples that contain at least 25 accepted images within
prefixes 25, 32, 48 and 64. A separate attack with an underfilled pool is not
fabricated; this distinguishes pool feasibility from selection-performance bias.

## E4 shared mechanism artifacts

Preparation and attack persist numeric artifacts required for the following
analyses before temporary images are cleaned:

### Key controls

- same-key centroid for each E2 strategy;
- deterministic shuffled-key centroid using the cyclic derangement
  `key_i -> key_(i+1 mod K)`;
- clean centroid from the full 25-image attacked clean prior.

The manifest records every source key and target key. Same-key and shuffled-key
quantities are never mixed in an attack target.

### Clean-set direction stability

The attacked removal direction uses the full locked 25-image clean prior, which
is exactly compatible with the immutable v1.22 `N=25`, `lambda=10000`,
`beta=1.5` baseline. As additional controls, construct five deterministic `N_c=5`
subsets using seeds 101, 103, 107, 109 and 113. Record for every subset:

- clean centroid norm;
- removal-direction norm;
- pairwise cosine similarity between directions;
- cosine similarity to the main direction;
- associated final detector score and detector-evasion outcome when available.

### Feature-matched and mismatched controls

Use the already locked Inception-v3 feature extractor. Rank the 25 clean-prior
images by feature distance to the mean feature of the selected watermarked
references, then compare the nearest five and farthest five. These conditions
must be named `inception_feature_matched` and `inception_feature_mismatched`;
they must not be described as proof of semantic equivalence.

### Detector association across optimization

Temporarily evaluate attack images at steps 0, 50, 100 and 150 in the evaluation
worker, never in the attack worker. Persist only hashes and numeric rows after
evaluation. Report:

- Spearman correlation between latent-to-target/centroid distance and detector
  score;
- correlation with task-oriented threshold margin;
- stratified results by watermark, model, task and E2 strategy;
- bootstrap confidence intervals clustered by key.

Correlations are evidence of association, not proof that the surrogate-VAE
centroid isolates a pure watermark component.

## Execution and retention

The run follows `prepare -> attack -> evaluate` in separate processes. It uses
the same exact-commit Tree-Ring regression, complete two-key smoke, explicit
formal approval, checkpoint/resume and offline-asset gates as the other formal
protocols. E2 selection tables and E4 mechanism tables are written separately.

Permanent artifacts include configs, protocol snapshot, run identity, full
candidate/selection manifests, per-key metrics, paired E2 tables, E4 numeric
controls, hashes, logs and summaries. Generated candidate, checkpoint-evaluation
and final-output images are temporary and may be deleted only after persistent
numeric rows and checksums pass their consumption gates.
