from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks.core.hashing import sha256_tree


def load_and_verify_assets(path: str | Path) -> dict[str, Any]:
    lock_path = Path(path)
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
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


def enforce_offline_environment() -> None:
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", DIFFUSERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
    )


def require_offline(flag: bool) -> None:
    if not flag:
        raise ValueError("Formal commands require --offline")
    enforce_offline_environment()
