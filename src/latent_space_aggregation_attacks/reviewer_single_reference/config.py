from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from ..core.hashing import stable_hash
from . import MODEL_ORDER, PROTOCOL_VERSION, TASK_ORDER, WATERMARK_ORDER
from .conditions import condition_registry, validate_registry

EXPECTED_METRICS = (
    "ASR", "LPIPS", "SSIM", "PSNR", "FID", "Time",
    "InitialScore", "FinalScore", "ThresholdMargin",
)


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("single-reference reviewer config must be a mapping")
    required = {
        "protocol_version", "run_mode", "master_seed", "output_root", "key_count",
        "model_settings", "watermarks", "tasks", "watermarked_reference_count",
        "clean_reference_values", "lambda_values", "beta_values", "main_N_clean",
        "main_lambda", "main_beta", "forgery_source_clean_index", "candidate_limit",
        "learning_rate", "steps", "resume_every", "attack_batch_size",
        "reference_encode_batch_size", "inversion_batch_size", "online_detection",
        "early_stop", "metrics", "watermark_runtime",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"single-reference config missing fields: {missing}")
    expected = {
        "protocol_version": PROTOCOL_VERSION,
        "master_seed": 205,
        "model_settings": list(MODEL_ORDER),
        "watermarks": list(WATERMARK_ORDER),
        "tasks": list(TASK_ORDER),
        "watermarked_reference_count": 1,
        "clean_reference_values": [1, 5, 25],
        "lambda_values": [10000.0, 20000.0, 50000.0],
        "beta_values": [1.0, 1.5, 2.0],
        "main_N_clean": 5,
        "main_lambda": 20000.0,
        "main_beta": 1.5,
        "forgery_source_clean_index": 0,
        "candidate_limit": 64,
        "learning_rate": 0.02,
        "steps": 150,
        "resume_every": 50,
        "attack_batch_size": 1,
        "reference_encode_batch_size": 1,
        "inversion_batch_size": 1,
        "online_detection": False,
        "early_stop": False,
        "metrics": list(EXPECTED_METRICS),
    }
    mismatches = {
        key: (value.get(key), wanted)
        for key, wanted in expected.items()
        if value.get(key) != wanted
    }
    if mismatches:
        raise ValueError(f"single-reference frozen setting mismatch: {mismatches}")
    mode = value["run_mode"]
    if mode not in {"smoke", "formal"}:
        raise ValueError("run_mode must be smoke or formal")
    if int(value["key_count"]) != (2 if mode == "smoke" else 200):
        raise ValueError("smoke/formal key_count must be 2/200")
    output = PurePosixPath(str(value["output_root"]))
    if not output.is_absolute() or output.name != "outputs":
        raise ValueError("output_root must be an absolute Linux path named outputs")
    for watermark in WATERMARK_ORDER:
        if watermark not in value["watermark_runtime"]:
            raise ValueError(f"missing watermark runtime: {watermark}")
    validate_registry(condition_registry())
    value["_source_path"] = str(source.resolve())
    value["resolved_config_hash"] = stable_hash({
        key: item for key, item in value.items() if not key.startswith("_")
    })
    return value


def compatibility_hash(config: dict[str, Any]) -> str:
    ignored = {"_source_path", "resolved_config_hash", "run_mode", "key_count"}
    return stable_hash({key: value for key, value in config.items() if key not in ignored})
