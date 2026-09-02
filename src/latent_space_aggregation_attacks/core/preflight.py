from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_config
from ..models.asset_lock import load_and_verify_assets, require_offline, validate_formal_assets


def preflight(config_path: str | Path, assets_lock: str | Path, *, offline: bool) -> dict[str, Any]:
    require_offline(offline)
    config = load_config(config_path)
    assets = load_and_verify_assets(assets_lock)
    if config["run_mode"] in {"formal", "smoke"}:
        validate_formal_assets(assets)
    return {"config": config, "assets": assets, "status": "PREFLIGHT_PASSED"}
