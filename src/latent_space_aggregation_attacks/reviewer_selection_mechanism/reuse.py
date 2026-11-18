from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable

from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file, stable_hash
from ..formal.common import atomic_csv, read_csv
from . import MODEL_ORDER, PROTOCOL_VERSION, WATERMARK_ORDER
from .common import keys


def _relative_image(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe candidate image path: {value}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise RuntimeError(f"candidate image escapes run directory: {value}")
    return resolved


def _read_valid_identity(source: Path) -> dict[str, Any]:
    path = source / "manifests/run_manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    recorded = value.pop("manifest_hash", None)
    if recorded != stable_hash(value):
        raise RuntimeError(f"source run manifest hash mismatch: {path}")
    if value.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("source candidate bank uses a different protocol")
    return value


def _validate_rows(
    rows: list[dict[str, str]], *, root: Path, model: str,
    watermark: str, key_id: str,
) -> None:
    if len(rows) != 64:
        raise RuntimeError(f"candidate group must contain 64 rows: {model}/{watermark}/{key_id}")
    indices = sorted(int(row["candidate_index"]) for row in rows)
    if indices != list(range(64)):
        raise RuntimeError(f"candidate indices are incomplete: {model}/{watermark}/{key_id}")
    for row in rows:
        expected = (row["model_setting"], row["watermark"], row["key_id"])
        if expected != (model, watermark, key_id):
            raise RuntimeError(f"candidate group identity mismatch: {expected}")
        image = _relative_image(root, row["image_path"])
        if not image.is_file() or sha256_file(image) != row["image_sha256"]:
            raise RuntimeError(f"candidate image hash mismatch: {image}")


def _materialize(source: Path, destination: Path, digest: str, copy: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != digest:
            raise RuntimeError(f"existing destination image is invalid: {destination}")
        return "existing"
    if copy:
        shutil.copy2(source, destination)
        mode = "copy"
    else:
        try:
            os.link(source, destination)
            mode = "hardlink"
        except OSError as exc:
            raise RuntimeError(
                "hard-link reuse failed; source and destination must be on the same "
                "filesystem, or rerun with --copy"
            ) from exc
    if sha256_file(destination) != digest:
        raise RuntimeError(f"destination image hash mismatch after {mode}: {destination}")
    return mode


def reuse_candidate_bank(
    *, source_run: str | Path, destination_run: str | Path,
    destination_run_id: str, key_count: int = 50, copy: bool = False,
    models: Iterable[str] = MODEL_ORDER,
    watermarks: Iterable[str] = WATERMARK_ORDER,
) -> dict[str, Any]:
    """Seed a new budget-profile run with verified candidate-bank units."""
    source = Path(source_run).resolve()
    destination = Path(destination_run).resolve()
    if source == destination:
        raise ValueError("source and destination runs must differ")
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("source and destination runs must not contain one another")
    if key_count != 50:
        raise ValueError("the budget profile is frozen at 50 keys")
    identity = _read_valid_identity(source)
    key_ids = keys(key_count)
    if not set(key_ids).issubset(set(identity.get("key_ids", []))):
        raise RuntimeError("source run does not contain all frozen budget-profile keys")

    destination_manifest = destination / "manifests/run_manifest.json"
    if destination_manifest.exists():
        existing = json.loads(destination_manifest.read_text(encoding="utf-8"))
        if existing.get("run_id") != destination_run_id:
            raise RuntimeError("destination is already bound to a different run ID")

    modes = {"hardlink": 0, "copy": 0, "existing": 0}
    group_count = 0
    image_count = 0
    source_unit_hashes: dict[str, str] = {}
    for model in tuple(models):
        for watermark in tuple(watermarks):
            for key_id in key_ids:
                name = f"{model}__{watermark}__{key_id}.csv"
                source_group = source / "manifests/candidate_bank_units" / name
                if not source_group.is_file():
                    raise FileNotFoundError(
                        f"source candidate group is not complete yet: {source_group}"
                    )
                rows = read_csv(source_group)
                _validate_rows(
                    rows, root=source, model=model,
                    watermark=watermark, key_id=key_id,
                )
                normalized = []
                for row in rows:
                    source_image = _relative_image(source, row["image_path"])
                    destination_image = _relative_image(destination, row["image_path"])
                    mode = _materialize(
                        source_image, destination_image, row["image_sha256"], copy,
                    )
                    modes[mode] += 1
                    normalized.append({**row, "run_id": destination_run_id})
                    image_count += 1
                destination_group = (
                    destination / "manifests/candidate_bank_units" / name
                )
                if destination_group.exists():
                    existing_rows = read_csv(destination_group)
                    _validate_rows(
                        existing_rows, root=destination, model=model,
                        watermark=watermark, key_id=key_id,
                    )
                    if existing_rows != normalized:
                        raise RuntimeError(
                            f"existing destination group differs: {destination_group}"
                        )
                else:
                    atomic_csv(destination_group, normalized)
                source_unit_hashes[name] = sha256_file(source_group)
                group_count += 1

    report = {
        "status": "COMPLETE",
        "protocol_version": PROTOCOL_VERSION,
        "execution_profile": "supplemental_50key_full_factorial",
        "source_run": str(source),
        "source_run_id": identity["run_id"],
        "source_manifest_hash": stable_hash(identity),
        "destination_run": str(destination),
        "destination_run_id": destination_run_id,
        "key_count": key_count,
        "candidate_group_count": group_count,
        "candidate_image_count": image_count,
        "materialization_counts": modes,
        "source_candidate_unit_hashes": source_unit_hashes,
    }
    atomic_write_json(destination / "manifests/candidate_bank_reuse.json", report)
    return report
