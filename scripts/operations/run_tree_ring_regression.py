from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.p0 import _assets_by_name, _encode, _open_rgb
from latent_space_aggregation_attacks.core.preflight import preflight
from latent_space_aggregation_attacks.core.seeds import configure_torch_determinism
from latent_space_aggregation_attacks.methods.proposed.optimizer import optimize_fixed_budget
from latent_space_aggregation_attacks.methods.proposed.targets import forgery_target
from latent_space_aggregation_attacks.models.loaders import load_proxy_vae, load_target_pipeline
from latent_space_aggregation_attacks.watermarks.runtime import image_to_tensor
from latent_space_aggregation_attacks.watermarks.tree_ring import TreeRingAdapter


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _max_image_difference(left, right) -> int:
    return int(np.abs(np.asarray(left, dtype=np.int16) - np.asarray(right, dtype=np.int16)).max())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GPU regression: compare v1.10 Tree-Ring and optimizer against the read-only legacy project"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--legacy-project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    import torch
    determinism = configure_torch_determinism(torch)

    checked = preflight(args.config, args.assets_lock, offline=args.offline)
    config = checked["config"]
    assets = _assets_by_name(checked["assets"])
    legacy_root = Path(args.legacy_project).resolve()
    if not (legacy_root / "rmlp" / "tree_ring.py").is_file():
        raise FileNotFoundError(legacy_root / "rmlp" / "tree_ring.py")
    sys.path.insert(0, str(legacy_root))
    legacy_tree = importlib.import_module("rmlp.tree_ring")
    legacy_attack = importlib.import_module("rmlp.attack")
    legacy_prototype = importlib.import_module("rmlp.prototype")
    legacy_image_io = importlib.import_module("rmlp.image_io")

    model = {
        "target_model_path": assets["stable-diffusion-2-base"]["path"],
        "proxy_vae_path": assets["stable-diffusion-v1-4"]["path"],
        "proxy_vae_subfolder": "vae", "dtype": "float16", "device": "cuda",
    }
    pipe = load_target_pipeline(model, offline=True)
    vae = load_proxy_vae(model, offline=True)
    runtime = dict(config["watermark_runtime"]["tree_ring"])
    runtime.update(pipe=pipe, code_revision="regression")
    new_adapter = TreeRingAdapter(runtime)

    legacy_config = {
        "watermark": {
            "w_seed": 0, "w_channel": 0, "w_radius": 16,
            "img_size": 512, "generation_steps": 50,
        }
    }
    old_key, old_mask = legacy_tree.build_key_and_mask(pipe, legacy_config)
    new_key = new_adapter.create_key({"watermark_seed": 0})
    key_max_abs = float((old_key - new_key["pattern"]).abs().max().item())
    mask_equal = bool((old_mask == new_key["mask"]).all().item())

    prompt_manifest = Path(assets["formal-protocol-v1.10-prompt-manifest"]["path"])
    prompt_rows = [
        row for row in _rows(prompt_manifest)
        if row["cohort"] == "pilot" and row["key_id"] == "pilot_key_000"
    ][:5]
    if len(prompt_rows) != 5:
        raise RuntimeError("Regression requires five pilot_key_000 prompts")

    new_images = []
    image_max_abs = []
    detector_abs = []
    for index, row in enumerate(prompt_rows):
        new_image = new_adapter.generate(row["prompt"], new_key, index)
        old_image = legacy_tree.generate_watermarked_image(
            pipe, row["prompt"], old_key, old_mask, 512, index, 50,
        )
        image_max_abs.append(_max_image_difference(new_image, old_image))
        new_score = new_adapter.detect(new_image, new_key).score
        old_score = legacy_tree.detect_p_value(new_image, pipe, old_key, old_mask, 512, 50)
        detector_abs.append(abs(float(new_score) - float(old_score)))
        new_images.append(new_image)

    new_latents = _encode(vae, new_images)
    old_latents = torch.cat([
        legacy_prototype.encode_vae_latent(
            vae, legacy_image_io.preprocess_pil(image, 512).unsqueeze(0)
        )
        for image in new_images
    ])
    new_target = forgery_target(new_latents)
    old_target = legacy_prototype.simple_average_prototype(old_latents).unsqueeze(0)
    target_max_abs = float((new_target - old_target).abs().max().item())

    coco_root = Path(assets["formal-protocol-v1.10-coco-manifests"]["path"])
    cover_row = _rows(coco_root / "p0_forgery_target_manifest.csv")[0]
    cover = _open_rgb(cover_row["path"])
    new_cover = image_to_tensor(cover, size=512, device="cuda", dtype=next(vae.parameters()).dtype)
    old_cover = legacy_image_io.preprocess_pil(cover, 512).unsqueeze(0).to(
        device="cuda", dtype=next(vae.parameters()).dtype
    )
    preprocess_max_abs = float((new_cover - old_cover).abs().max().item())
    old_result = legacy_attack.optimize_to_target_latent(
        old_cover, old_target, vae, lambda_pixel=10000.0, alpha=0.02,
        num_iterations=10, log_every=10,
    )
    # The preceding checks establish equivalence of the independently built
    # tensors. Use the same objects here so this gate isolates the update rule.
    new_result = optimize_fixed_budget(
        old_cover, old_target, vae, lambda_pixel=10000.0, learning_rate=0.02,
        final_step=10,
    )
    attack_max_abs = float((new_result.image - old_result.adversarial).abs().max().item())

    report = {
        "status": "PASSED",
        "tree_ring": {"channel": 0, "radius": 16},
        "torch_determinism": determinism,
        "key_max_abs": key_max_abs,
        "mask_equal": mask_equal,
        "image_max_abs_per_reference": image_max_abs,
        "detector_score_abs_per_reference": detector_abs,
        "target_max_abs": target_max_abs,
        "preprocess_max_abs": preprocess_max_abs,
        "attack_10step_max_abs": attack_max_abs,
        "tolerances": {
            "key": 1e-6, "image_uint8": 0, "detector": 1e-10,
            "target": 1e-6, "preprocess": 0.0, "attack": 1e-6,
        },
    }
    failures = []
    if key_max_abs > 1e-6 or not mask_equal: failures.append("key_or_mask")
    if max(image_max_abs) != 0: failures.append("generated_image")
    if max(detector_abs) > 1e-10: failures.append("detector")
    if target_max_abs > 1e-6: failures.append("target")
    if preprocess_max_abs != 0.0: failures.append("preprocess")
    if attack_max_abs > 1e-6: failures.append("optimizer")
    if failures:
        report.update(status="FAILED", failures=failures)
    atomic_write_json(args.output, report)
    print(json.dumps(report, indent=2))
    if failures:
        raise RuntimeError(f"Tree-Ring regression failed: {failures}")


if __name__ == "__main__":
    main()
