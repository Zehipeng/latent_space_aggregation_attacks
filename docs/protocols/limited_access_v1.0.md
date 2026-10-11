# Limited-access supplementary experiment v1.0

This protocol is an additional experiment and does not modify or replace
`formal_protocol_v1.22` or any E0--E7 result.

## Question and scope

Test whether removal and forgery remain possible when an attacker has exactly
one watermarked image for a key and five unpaired clean images.  The experiment
uses 200 keys and the cross-model setting only: SD v2.0 generates and detects
the watermark, while the SD v1.4 VAE is the public proxy.

Watermarks run sequentially in one orchestrator: Tree-Ring, RingID, then
Gaussian Shading.  A low attack-success rate is a result, not a pipeline gate.
Only a technical failure, integrity failure, or failed prerequisite stops the
sequence.

## Frozen inputs and targets

For each key, select the first accepted watermarked candidate from the frozen
64-candidate manifest.  Let its proxy-VAE latent be `z_w`.  Use the first five
images of that key's preregistered, non-overlapping clean-prior group and define

`z_bar_c = FP32_mean(E(x_c1), ..., E(x_c5))`, and `d = z_w - z_bar_c`.

No filtering, weighting, normalization, semantic pairing, or detector-based
selection is permitted.  `x_c1` is both a member of the five-image mean and the
forgery source image.

Removal starts from `x_w` and targets `z_w - beta*d`.  Forgery starts from
`x_c1` and targets `E(x_c1) + beta*d`.

Both tasks minimize the existing detector-free pixel-space objective

`MSE(E(x), z_target) + lambda_pixel*MSE(x, x_source)`.

Frozen values are `beta=1.5`, `lambda_pixel=20000`, learning rate `0.02`, 150
steps, scalar attack/reference/inversion batches, checkpoint interval 50, and
master seed 205.  Attacks make no detector queries and do not early-stop.

## Detection and outcomes

Use the repository's pinned official-compatible implementations and frozen
thresholds. Tree-Ring and RingID accept when `p <= 0.05`. Gaussian Shading
accepts when bit accuracy is at least `0.6484375` (registered FPR `1e-6`).

Forgery is eligible when the clean source is rejected and succeeds when the
final image is accepted. Removal is eligible when the watermarked source is
accepted and succeeds when the final image is rejected. For Tree-Ring and
RingID, the inherited removal boundary is `p >= 0.05`; exact equality must be
recorded.

## Outputs and gates

Permanent numerical outputs include per-key initial/final detector scores,
eligibility, success, ASR summaries, LPIPS, SSIM, PSNR, FID, attack time,
failures, ineligible samples, anomalies, manifests, hashes, runtime metadata,
and the experiment summary. L2 and Linf must not be computed or emitted.

The 2-key smoke contains 12 final outputs (3 watermarks x 2 tasks x 2 keys).
It must complete on the actual server GPU and produce P50/P90 ETA, peak GPU
memory, and disk reports. A separate invocation with explicit approval is
required before the 200-key run. The formal run contains 1,200 final outputs.
Temporary reference and attack PNGs are removed only after numerical outputs
and hashes are verified.
