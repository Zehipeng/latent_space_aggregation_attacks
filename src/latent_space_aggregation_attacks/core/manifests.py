from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .atomic_io import atomic_write_json
from .hashing import sha256_file, stable_hash

REQUIRED_MANIFESTS = (
    "run_manifest.json", "key_manifest.json", "sample_manifest.csv",
    "reference_manifest.csv", "clean_prior_manifest.csv",
)


def validate_nested_indices(rows: Iterable[dict[str, Any]], *, group_field: str = "key_id") -> None:
    grouped: dict[str, set[int]] = {}
    for row in rows:
        grouped.setdefault(str(row[group_field]), set()).add(int(row["reference_index"]))
    for key, indices in grouped.items():
        if not set(range(25)).issubset(indices):
            raise ValueError(f"{key} does not contain ordered indices 0..24")


def ensure_disjoint(left_ids: Iterable[str], right_ids: Iterable[str], label: str) -> None:
    overlap = set(left_ids) & set(right_ids)
    if overlap:
        raise ValueError(f"{label} overlap: {sorted(overlap)[:5]}")


def write_manifest(path: str | Path, payload: dict[str, Any]) -> str:
    value = dict(payload)
    value["manifest_hash"] = stable_hash(payload)
    atomic_write_json(path, value)
    return sha256_file(path)


def read_csv_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_run_manifests(run_dir: str | Path) -> None:
    root = Path(run_dir) / "manifests"
    missing = [name for name in REQUIRED_MANIFESTS if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing manifests: {missing}")
    run_manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    recorded = run_manifest.pop("manifest_hash", None)
    if recorded != stable_hash(run_manifest):
        raise ValueError("run_manifest hash mismatch")

