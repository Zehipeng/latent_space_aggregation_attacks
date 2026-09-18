from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.hashing import stable_hash
from ..formal.prepare import prepare_formal_removal


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
    result = prepare_formal_removal(config=selected, assets_lock=assets,
        run_dir=root / "shared_preparation", run_id=run_id,
        key_ids=settings["key_ids"], project_root=project)
    print(result, flush=True)
