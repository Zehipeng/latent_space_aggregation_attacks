from __future__ import annotations

from pathlib import Path
from typing import Iterable


def validate_trajectory_rows(rows: Iterable[dict], key_count: int, steps: list[int]) -> None:
    records = list(rows)
    expected = key_count * len(steps)
    if len(records) != expected:
        raise ValueError(f"Expected {expected} trajectory rows, got {len(records)}")
    observed = {(row["key_id"], int(row["step"])) for row in records}
    expected_pairs = {(f"key_{key:03d}", step) for key in range(key_count) for step in steps}
    if observed != expected_pairs:
        raise ValueError("Trajectory key/step grid is incomplete")


def cleanup_verified_spool(spool: str | Path, *, verified: bool, keep_keys: set[str]) -> list[str]:
    if not verified:
        raise ValueError("Spool cleanup requires verified CSV rows, hashes, and figures")
    removed: list[str] = []
    root = Path(spool)
    for path in root.rglob("*.png"):
        if not any(key in path.parts or key in path.name for key in keep_keys):
            path.unlink(); removed.append(str(path))
    return removed

