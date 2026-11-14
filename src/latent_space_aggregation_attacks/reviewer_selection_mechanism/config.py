from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from ..core.hashing import stable_hash
from . import MODEL_ORDER, PROTOCOL_VERSION, TASK_ORDER, WATERMARK_ORDER
from .conditions import condition_registry, validate_registry


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("E2/E4 config must be a mapping")
    expected = {
        "protocol_version": PROTOCOL_VERSION,
        "master_seed": 205,
        "model_settings": list(MODEL_ORDER),
        "watermarks": list(WATERMARK_ORDER),
        "tasks": list(TASK_ORDER),
        "candidate_limit": 64,
        "watermarked_reference_count": 25,
        "clean_reference_count": 5,
        "lambda_pixel": 20000.0,
        "beta": 1.5,
        "selection_strategy_seeds": [17, 29, 43],
        "clean_subset_seeds": [101, 103, 107, 109, 113],
        "learning_rate": 0.02,
        "steps": 150,
        "resume_every": 50,
        "attack_batch_size": 1,
        "reference_encode_batch_size": 1,
        "inversion_batch_size": 1,
        "online_detection": False,
        "early_stop": False,
    }
    missing = sorted(set(expected) - set(value))
    if missing:
        raise ValueError(f"E2/E4 config missing fields: {missing}")
    wrong = {
        key: (value.get(key), wanted)
        for key, wanted in expected.items()
        if value.get(key) != wanted
    }
    if wrong:
        raise ValueError(f"E2/E4 frozen setting mismatch: {wrong}")
    mode = value.get("run_mode")
    if mode not in {"smoke", "formal"}:
        raise ValueError("run_mode must be smoke or formal")
    if int(value.get("key_count", -1)) != (2 if mode == "smoke" else 200):
        raise ValueError("smoke/formal key_count must be 2/200")
    output = PurePosixPath(str(value.get("output_root", "")))
    if not output.is_absolute() or output.name != "outputs":
        raise ValueError("output_root must be an absolute Linux path named outputs")
    if set(value.get("watermark_runtime", {})) != set(WATERMARK_ORDER):
        raise ValueError("watermark_runtime must contain exactly the three watermarks")
    validate_registry(condition_registry())
    value["_source_path"] = str(source.resolve())
    value["resolved_config_hash"] = stable_hash({
        key: item for key, item in value.items() if not key.startswith("_")
    })
    return value


def compatibility_hash(config: dict[str, Any]) -> str:
    ignored = {"_source_path", "resolved_config_hash", "run_mode", "key_count"}
    return stable_hash({key: value for key, value in config.items() if key not in ignored})
