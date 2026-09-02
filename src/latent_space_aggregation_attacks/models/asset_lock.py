from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks.core.hashing import TREE_HASH_POLICY, sha256_tree

FORMAL_REQUIRED_ASSETS = {
    "stable-diffusion-v1-4": "133a221b8aa7292a167afc5127cb63fb5005638b",
    "stable-diffusion-2-base": "f5bc1bd97485577aa0b946fa8a9004e2ec147402",
    "tree-ring-watermark": "3015283d9cf82e90b628f02ad2121bd37408ca9a",
    "RingID": "45631a59aecd7d63ccdb640aaaf3e616fdb89fb9",
    "Gaussian-Shading": "09c678fadc7545acf7be12647ddf2a5e66f6a9dc",
    "formal-protocol-v1.10-prompt-manifest": "formal_protocol_v1.10",
    "formal-protocol-v1.10-coco-manifests": "formal_protocol_v1.10",
    "lpips-alex-v0.1": "lpips-0.1.4-v0.1",
    "alexnet-imagenet1k": "torchvision-0.16.2-IMAGENET1K_V1",
    "inception-v3-imagenet1k": "torchvision-0.16.2-IMAGENET1K_V1",
}


def load_and_verify_assets(path: str | Path) -> dict[str, Any]:
    lock_path = Path(path)
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2 or payload.get("hash_policy") != TREE_HASH_POLICY:
        raise ValueError("Unsupported or legacy asset-lock hash policy; regenerate the lock")
    assets = payload.get("assets", [])
    if not assets:
        raise ValueError("assets.lock.json has no assets")
    for asset in assets:
        local_path = Path(asset["path"])
        if not local_path.exists():
            raise FileNotFoundError(local_path)
        actual_hash, actual_size, actual_files = sha256_tree(local_path)
        if asset.get("sha256") != actual_hash:
            raise ValueError(f"Asset checksum mismatch: {local_path}")
        if int(asset.get("size_bytes", -1)) != actual_size or int(asset.get("file_count", -1)) != actual_files:
            raise ValueError(f"Asset size/count mismatch: {local_path}")
        if not asset.get("revision") and asset.get("kind") in {"model", "watermark_code"}:
            raise ValueError(f"Unpinned asset: {asset['name']}")
    return payload


def validate_formal_assets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_name = {str(asset["name"]): asset for asset in payload.get("assets", [])}
    missing = sorted(set(FORMAL_REQUIRED_ASSETS) - set(by_name))
    if missing:
        raise ValueError(f"Formal assets lock is missing required entries: {missing}")
    for name, revision in FORMAL_REQUIRED_ASSETS.items():
        if by_name[name].get("revision") != revision:
            raise ValueError(f"Formal asset {name} must use revision {revision}")
    return by_name


def enforce_offline_environment() -> None:
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", DIFFUSERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
    )


def require_offline(flag: bool) -> None:
    if not flag:
        raise ValueError("Formal commands require --offline")
    enforce_offline_environment()
