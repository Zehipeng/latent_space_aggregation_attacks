from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks.core.hashing import sha256_file


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
        if local_path.is_file() and asset.get("sha256") != sha256_file(local_path):
            raise ValueError(f"Asset checksum mismatch: {local_path}")
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

