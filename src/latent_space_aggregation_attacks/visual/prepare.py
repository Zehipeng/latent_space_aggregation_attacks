from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.hashing import stable_hash
from ..formal.prepare import prepare_formal_removal
from .content import build_inputs, freeze_originals


def prepare(config: dict[str, Any], assets: dict[str, Any], root: Path,
            run_id: str, project: Path, settings: dict[str, Any]) -> None:
    # Shared RingID references and first-reference removal targets. Filter only
    # after validating the original protocol config; never edit formal config.
    selected = dict(config)
    selected["model_settings"] = [settings["model_setting"]]
    selected["watermarks"] = [settings["watermark"]]
    selected["resolved_config_hash"] = stable_hash({k: v for k, v in selected.items()
                                                   if k != "resolved_config_hash"})
    print(f"VISUAL_PREPARE_START: {len(settings['key_ids'])} keys, RingID, 25 accepted references per key", flush=True)
    inputs = build_inputs(assets, settings)
    selected["resolved_config_hash"] = stable_hash({"preparation": selected["resolved_config_hash"], "visual_settings": settings})
    result = prepare_formal_removal(config=selected, assets_lock=assets,
        run_dir=root / "shared_preparation", run_id=run_id,
        key_ids=settings["key_ids"], project_root=project, input_overrides=inputs)
    freeze_originals(root, settings, inputs[1])
    print(result, flush=True)
