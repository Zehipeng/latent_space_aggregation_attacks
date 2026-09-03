from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from latent_space_aggregation_attacks import PROTOCOL_VERSION

from ..core.atomic_io import atomic_write_bytes, atomic_write_json
from ..core.hashing import sha256_file, stable_hash
from ..core.manifests import write_manifest

MODEL_REVISIONS = {
    "stable-diffusion-v1-4": "133a221b8aa7292a167afc5127cb63fb5005638b",
    "stable-diffusion-2-base": "f5bc1bd97485577aa0b946fa8a9004e2ec147402",
}
WATERMARK_REVISIONS = {
    "tree_ring": "3015283d9cf82e90b628f02ad2121bd37408ca9a",
    "ringid": "45631a59aecd7d63ccdb640aaaf3e616fdb89fb9",
    "gaussian_shading": "09c678fadc7545acf7be12647ddf2a5e66f6a9dc",
}
WATERMARK_ASSET_NAMES = {
    "tree_ring": "tree-ring-watermark",
    "ringid": "RingID",
    "gaussian_shading": "Gaussian-Shading",
}


def git_sha(project_root: str | Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, check=True,
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_csv(path: str | Path, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> None:
    records = list(rows)
    if not records and fields is None:
        raise ValueError(f"Cannot infer fields for empty CSV: {path}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    columns = fields or list(records[0])
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
        handle.flush()
    temporary.replace(destination)


def assets_by_name(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in lock["assets"]}


def target_model_asset(model_setting: str) -> str:
    if model_setting == "same_model_sd14_target_sd14_vae_proxy":
        return "stable-diffusion-v1-4"
    if model_setting == "cross_model_sd2_target_sd14_vae_proxy":
        return "stable-diffusion-2-base"
    raise ValueError(model_setting)


def model_config(assets: dict[str, dict[str, Any]], model_setting: str) -> dict[str, Any]:
    target = target_model_asset(model_setting)
    return {
        "target_model_path": assets[target]["path"],
        "proxy_vae_path": assets["stable-diffusion-v1-4"]["path"],
        "proxy_vae_subfolder": "vae",
        "dtype": "float16",
        "device": "cuda",
    }


def adapter_config(config: dict[str, Any], watermark: str, pipe: Any, assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    locked = assets[WATERMARK_ASSET_NAMES[watermark]]
    expected = WATERMARK_REVISIONS[watermark]
    if locked.get("revision") != expected:
        raise ValueError(f"{watermark} revision must be {expected}")
    runtime = dict(config["watermark_runtime"][watermark])
    runtime.update(pipe=pipe, code_revision=expected, code_path=locked["path"])
    return runtime


def threshold(config: dict[str, Any], watermark: str) -> float:
    runtime = config["watermark_runtime"][watermark]
    field = "bit_accuracy_threshold" if watermark == "gaussian_shading" else "p_value_threshold"
    return float(runtime[field])


def open_rgb(path: str | Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB").copy()


def canonical_512(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    scale = 512 / min(rgb.size)
    resized = rgb.resize(
        (round(rgb.width * scale), round(rgb.height * scale)), Image.Resampling.BICUBIC,
    )
    left, top = (resized.width - 512) // 2, (resized.height - 512) // 2
    return resized.crop((left, top, left + 512, top + 512))


def png_payload(image: Image.Image) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    payload = buffer.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def atomic_png(path: str | Path, image: Image.Image) -> str:
    payload, digest = png_payload(image)
    atomic_write_bytes(path, payload)
    return digest


def formal_inputs(assets: dict[str, dict[str, Any]]) -> tuple[
    dict[str, list[dict[str, str]]], dict[str, dict[str, str]], dict[str, list[dict[str, str]]]
]:
    prompt_rows = read_csv(assets["formal-protocol-v1.10-prompt-manifest"]["path"])
    prompts: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in prompt_rows:
        if row["cohort"] == "formal":
            prompts[row["key_id"]].append(row)
    for rows in prompts.values():
        rows.sort(key=lambda row: int(row["reference_index"]))
    coco_root = Path(assets["formal-protocol-v1.10-coco-manifests"]["path"])
    targets = {row["key_id"]: row for row in read_csv(coco_root / "formal_forgery_target_manifest.csv")}
    clean: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(coco_root / "formal_clean_prior_manifest.csv"):
        clean[row["key_id"]].append(row)
    for rows in clean.values():
        rows.sort(key=lambda row: int(row["clean_index"]))
    if len(prompts) != 200 or len(targets) != 200 or len(clean) != 200:
        raise ValueError("Formal manifests must contain exactly 200 keys")
    if any(len(rows) != 64 for rows in prompts.values()):
        raise ValueError("Every formal key must have exactly 64 prompt candidates")
    if any(len(rows) != 25 for rows in clean.values()):
        raise ValueError("Every formal key must have exactly 25 clean priors")
    return prompts, targets, clean


RUN_SUBDIRS = (
    "protocol_snapshot", "manifests", "logs", "prepared_inputs", "resume_state",
    "checkpoints_visualization_keys", "final_images_visualization_keys",
    "evaluation_spool", "evaluation", "figures",
)


def ensure_run_layout(run_dir: str | Path) -> Path:
    root = Path(run_dir)
    for name in RUN_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def bind_run_identity(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    if destination.is_file():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        recorded = existing.pop("manifest_hash", None)
        if recorded != stable_hash(existing):
            raise ValueError("Existing formal run manifest is corrupt")
        if existing != payload:
            raise RuntimeError("Formal run identity changed; use a new run-id")
        return
    write_manifest(destination, payload)


def run_identity(
    *, config: dict[str, Any], assets_lock: dict[str, Any], project_root: str | Path,
    run_id: str, key_ids: list[str], task: str,
) -> dict[str, Any]:
    assets = assets_by_name(assets_lock)
    prompts, targets, clean = formal_inputs(assets)
    # Bind smoke and full execution to the same complete preregistered sample
    # universe.  The key_ids field still records which subset this run consumes.
    all_keys = [f"key_{index:03d}" for index in range(200)]
    selected = {
        "prompts": [row for key in all_keys for row in prompts[key]],
        "targets": [targets[key] for key in all_keys],
        "clean": [row for key in all_keys for row in clean[key]],
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "task": task,
        "git_sha": git_sha(project_root),
        "resolved_config_hash": formal_compatibility_hash(config),
        "source_resolved_config_hash": config["resolved_config_hash"],
        "assets_lock_hash": stable_hash(assets_lock),
        "sample_manifest_hash": stable_hash(selected),
        "key_ids": key_ids,
    }


def formal_compatibility_hash(config: dict[str, Any]) -> str:
    ignored = {"_source_path", "resolved_config_hash", "run_mode", "key_count"}
    return stable_hash({key: value for key, value in config.items() if key not in ignored})


def verified_rows(path: str | Path, run_dir: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        return []
    valid = []
    for row in read_csv(source):
        relative = row.get("output_image_path", "")
        output = Path(run_dir) / relative
        if relative and output.is_file() and sha256_file(output) == row.get("output_sha256"):
            valid.append(row)
    return valid
