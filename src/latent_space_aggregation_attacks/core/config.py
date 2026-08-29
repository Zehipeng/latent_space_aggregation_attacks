from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from latent_space_aggregation_attacks import MASTER_SEED, PROTOCOL_VERSION
from .hashing import stable_hash

MODEL_SETTINGS = {
    "same_model_sd14_target_sd14_vae_proxy",
    "cross_model_sd2_target_sd14_vae_proxy",
}
WATERMARKS = {"tree_ring", "ringid", "gaussian_shading"}


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a mapping")
    config = deepcopy(value)
    config["_source_path"] = str(source)
    validate_config(config)
    config["resolved_config_hash"] = stable_hash({k: v for k, v in config.items() if not k.startswith("_")})
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError(f"protocol_version must be {PROTOCOL_VERSION}")
    if int(config.get("master_seed", -1)) != MASTER_SEED:
        raise ValueError(f"master_seed must be {MASTER_SEED}")
    mode = config.get("run_mode")
    if mode not in {"budget_pilot", "budget_confirmation", "smoke", "formal"}:
        raise ValueError("Invalid run_mode")
    settings = set(config.get("model_settings", []))
    if mode in {"budget_pilot", "budget_confirmation"}:
        if settings != {"cross_model_sd2_target_sd14_vae_proxy"}:
            raise ValueError("P0 permits only the cross-model setting")
    elif not settings or not settings.issubset(MODEL_SETTINGS):
        raise ValueError("Formal/smoke model settings are invalid")
    if set(config.get("watermarks", [])) != WATERMARKS:
        raise ValueError("All three registered watermarks are required")
    if int(config.get("key_count", 0)) not in ({100} if mode in {"budget_pilot", "budget_confirmation"} else {2, 200}):
        raise ValueError("key_count does not match the run mode")
    if config.get("N_values") != [1, 5, 25]:
        raise ValueError("N_values must be [1, 5, 25]")
    if config.get("lambda_values") != [10000.0, 20000.0, 50000.0]:
        raise ValueError("lambda_values do not match the protocol")
    if config.get("beta_values") != [0.5, 1.0, 2.0]:
        raise ValueError("beta_values do not match the protocol")
    if float(config.get("learning_rate", -1)) != 0.02:
        raise ValueError("learning_rate must be 0.02")
    if int(config.get("resume_every", -1)) != 50:
        raise ValueError("resume_every must be 50")
    if mode in {"formal", "smoke"}:
        if config.get("T_formal") in {None, "UNFROZEN"}:
            raise ValueError("T_formal is not frozen; formal execution is prohibited")
        if config.get("online_detection", False) or config.get("early_stop", False):
            raise ValueError("Formal attack must not use online detection or early stopping")
    if mode == "budget_pilot":
        if int(config.get("T_max", 0)) != 1500 or int(config.get("detection_every", 0)) != 100:
            raise ValueError("P0 requires T_max=1500 and detection_every=100")
        if not config.get("online_detection") or not config.get("early_stop"):
            raise ValueError("P0 online stage requires detection and early stopping")

