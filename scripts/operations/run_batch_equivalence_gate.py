from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.formal_common import (
    adapter_config, assets_by_name, canonical_512, formal_inputs, git_sha, model_config, open_rgb,
)
from latent_space_aggregation_attacks.core.hashing import stable_hash
from latent_space_aggregation_attacks.core.preflight import preflight
from latent_space_aggregation_attacks.core.seeds import configure_torch_determinism, derive_seed
from latent_space_aggregation_attacks.methods.proposed.optimizer import (
    optimize_fixed_budget, optimize_fixed_budget_batch,
)
from latent_space_aggregation_attacks.models.loaders import load_proxy_vae, load_target_pipeline
from latent_space_aggregation_attacks.watermarks.base import registered_adapter
from latent_space_aggregation_attacks.watermarks.runtime import image_to_tensor


def main() -> None:
    parser = argparse.ArgumentParser(description="GPU scalar-vs-batch equivalence gate")
    parser.add_argument("--config", required=True)
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    import torch

    determinism = configure_torch_determinism(torch)
    checked = preflight(args.config, args.assets_lock, offline=args.offline)
    config = checked["config"]
    assets = assets_by_name(checked["assets"])
    _, target_by_key, _ = formal_inputs(assets)
    batching = config["validated_batching"]
    attack_batch_size = int(batching["attack_batch_size"])
    inversion_batch_size = int(batching["inversion_batch_size"])
    key_ids = [f"key_{index:03d}" for index in range(max(attack_batch_size, inversion_batch_size))]
    images = [canonical_512(open_rgb(target_by_key[key_id]["path"])) for key_id in key_ids]

    vae = load_proxy_vae(model_config(assets, "same_model_sd14_target_sd14_vae_proxy"), offline=True)
    dtype = next(vae.parameters()).dtype
    attack_images = torch.cat([
        image_to_tensor(image, size=512, device="cuda", dtype=dtype)
        for image in images[:attack_batch_size]
    ])
    with torch.inference_mode():
        targets = vae.encode(attack_images.roll(1, 0)).latent_dist.mode() * (
            1.0 / float(vae.config.scaling_factor)
        )
    lambdas = [10000.0, 20000.0, 50000.0, 10000.0][:attack_batch_size]
    scalar_outputs = []
    for index in range(attack_batch_size):
        scalar_outputs.append(optimize_fixed_budget(
            attack_images[index:index + 1], targets[index:index + 1], vae,
            lambda_pixel=lambdas[index], learning_rate=0.02, final_step=3,
        ).image)
    scalar_attack = torch.cat(scalar_outputs)
    batched_attack = optimize_fixed_budget_batch(
        attack_images, targets, vae, lambda_pixels=lambdas,
        learning_rate=0.02, final_step=3,
    ).images
    attack_max_abs = float((scalar_attack - batched_attack).abs().max().item())
    del vae, attack_images, targets, scalar_attack, batched_attack
    torch.cuda.empty_cache()

    inversion_results = []
    inversion_tolerance = 2e-4
    score_tolerance = 1e-5
    decisions_equal = True
    for model_setting in config["model_settings"]:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        runtime = dict(config["watermark_runtime"]["tree_ring"])
        runtime.update(pipe=pipe, code_revision="batch-equivalence")
        inversion_adapter = registered_adapter("tree_ring", runtime)
        scalar = torch.cat([inversion_adapter.invert(image) for image in images[:inversion_batch_size]])
        batched = inversion_adapter.invert_many(images[:inversion_batch_size])
        inversion_max_abs = float((scalar - batched).abs().max().item())
        for watermark in config["watermarks"]:
            adapter = registered_adapter(watermark, adapter_config(config, watermark, pipe, assets))
            key_id = key_ids[0]
            key = adapter.create_key({
                "key_id": key_id,
                "watermark_seed": derive_seed("watermark_key", watermark, key_id),
            })
            scalar_score = adapter.detect_inverted(scalar[0:1], key)
            batch_score = adapter.detect_inverted(batched[0:1], key)
            score_abs = abs(float(scalar_score.score) - float(batch_score.score))
            equal = bool(scalar_score.accepted == batch_score.accepted)
            decisions_equal = decisions_equal and equal
            inversion_results.append({
                "model_setting": model_setting, "watermark": watermark,
                "inversion_max_abs": inversion_max_abs, "detector_score_abs": score_abs,
                "scalar_accepted": scalar_score.accepted, "batch_accepted": batch_score.accepted,
                "decision_equal": equal,
            })
        del pipe, scalar, batched
        torch.cuda.empty_cache()

    failures = []
    if attack_max_abs > 5e-5:
        failures.append("attack_tensor_difference")
    if any(row["inversion_max_abs"] > inversion_tolerance for row in inversion_results):
        failures.append("inversion_tensor_difference")
    if any(row["detector_score_abs"] > score_tolerance for row in inversion_results):
        failures.append("detector_score_difference")
    if not decisions_equal:
        failures.append("acceptance_decision_difference")
    report = {
        "status": "FAILED" if failures else "PASSED",
        "protocol_version": config["protocol_version"],
        "git_sha": git_sha(PROJECT_ROOT),
        "source_resolved_config_hash": config["resolved_config_hash"],
        "assets_lock_hash": stable_hash(checked["assets"]),
        "validated_batching": batching,
        "torch_determinism": determinism,
        "gpu_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "attack_three_step_max_abs": attack_max_abs,
        "inversion_results": inversion_results,
        "tolerances": {"attack": 5e-5, "inversion": inversion_tolerance, "detector_score": score_tolerance},
        "failures": failures,
    }
    atomic_write_json(args.output, report)
    print(json.dumps(report, indent=2))
    if failures:
        raise RuntimeError(f"Batch equivalence gate failed: {failures}")


if __name__ == "__main__":
    main()
