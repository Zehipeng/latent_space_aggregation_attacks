from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from ..core.hashing import sha256_file

MODEL = "cross_model_sd2_target_sd14_vae_proxy"
EXPECTED = {
    "experiment_version": "visual_ablation_v2", "method_label": "FR-LA",
    "watermark": "ringid", "model_setting": MODEL,
    "key_ids": [f"key_{i:03d}" for i in range(2, 12)],
    "group_keys": {
        "forgery_lambda": ["key_002", "key_003"],
        "forgery_N": ["key_004", "key_005"],
        "removal_lambda": ["key_006", "key_007"],
        "removal_N": ["key_008", "key_009"],
        "removal_beta": ["key_010", "key_011"],
    }, "N_values": [1, 5, 25],
    "lambda_values": [10000.0, 20000.0, 50000.0], "beta_values": [1.0, 1.5, 2.0],
    "main_N": 5, "main_lambda": 10000.0, "main_beta": 1.5,
    "iterations": 150, "learning_rate": 0.02,
    "save_difference": False,
}


def load_settings(path: str | Path) -> dict[str, Any]:
    settings = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if settings != EXPECTED:
        raise ValueError("Visual settings differ from the user-approved visual_ablation_v2 contract")
    return settings


def plan(settings: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep every figure view while executing each shared physical condition once."""
    unique: dict[str, dict[str, Any]] = {}
    views = []
    for task in ("forgery", "removal"):
        for factor in (("lambda", "N") if task == "forgery" else ("lambda", "N", "beta")):
            for value in settings[f"{factor}_values"]:
                n, lam, beta = settings["main_N"], settings["main_lambda"], settings["main_beta"]
                if factor == "N": n = value
                if factor == "lambda": lam = value
                if factor == "beta": beta = value
                group = f"{task}_{factor}"
                cid = f"{group}_N{n}_lambda{int(lam)}" + (f"_beta{beta:g}" if task == "removal" else "")
                unique[cid] = {"condition_id": cid, "task": task, "N": n,
                               "group": group, "key_ids": settings["group_keys"][group],
                               "lambda": lam, "beta": beta if task == "removal" else None}
                for key in settings["group_keys"][group]:
                    views.append({"group": f"{task}_{factor}", "factor": factor,
                                  "value": value, "condition_id": cid, "key_id": key})
    return list(unique.values()), views


def semantic_difference(final: Image.Image, original: Image.Image) -> Image.Image:
    """Match semantic-forgery's ToTensor -> abs -> ToPILImage float conversion.

    RGB values become float32 [0,1], then abs differences are multiplied by 255
    and truncated to uint8, without amplification or per-image normalization.
    """
    if final.size != original.size:
        raise ValueError("Difference images require identical dimensions")
    a = np.asarray(final.convert("RGB"), dtype=np.float32) / 255.0
    b = np.asarray(original.convert("RGB"), dtype=np.float32) / 255.0
    return Image.fromarray((np.abs(a - b) * 255.0).astype(np.uint8))


def verified_record(path: Path, root: Path) -> dict[str, Any] | None:
    if not path.is_file(): return None
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        for name in ("original", "final"):
            file = root / row[f"{name}_path"]
            if not file.is_file() or sha256_file(file) != row[f"{name}_sha256"]:
                return None
        return row
    except (KeyError, ValueError, OSError):
        return None
