from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..core.hashing import stable_hash
from ..core.manifests import write_manifest
from ..formal.common import assets_by_name, formal_inputs
from . import PROTOCOL_VERSION
from .config import compatibility_hash


def git_sha(project: str | Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def keys(count: int) -> list[str]:
    return [f"key_{index:03d}" for index in range(count)]


def identity(
    config: dict[str, Any], lock: dict[str, Any], project: str | Path,
    run_id: str, key_ids: list[str],
) -> dict[str, Any]:
    assets = assets_by_name(lock)
    prompts, _, clean = formal_inputs(assets)
    all_keys = keys(200)
    universe = {
        "prompts": [row for key in all_keys for row in prompts[key]],
        "clean": [row for key in all_keys for row in clean[key][:25]],
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "git_sha": git_sha(project),
        "resolved_config_hash": compatibility_hash(config),
        "source_resolved_config_hash": config["resolved_config_hash"],
        "assets_lock_hash": stable_hash(lock),
        "sample_manifest_hash": stable_hash(universe),
        "key_ids": key_ids,
    }


def bind_identity(path: Path, value: dict[str, Any]) -> None:
    if path.is_file():
        old = json.loads(path.read_text(encoding="utf-8"))
        digest = old.pop("manifest_hash", None)
        if digest != stable_hash(old) or old != value:
            raise RuntimeError("run identity changed or existing manifest is corrupt")
    else:
        write_manifest(path, value)


def layout(root: Path) -> Path:
    for name in (
        "protocol_snapshot", "manifests", "logs", "prepared_inputs",
        "resume_state", "evaluation_spool", "evaluation",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
