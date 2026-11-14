from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file
from ..core.seeds import derive_seed
from ..formal.common import atomic_csv, read_csv
from .analysis import paired_strategy_differences


def _verified_checksum(run: Path, relative: str) -> str:
    checksums = run / "checksums.sha256"
    if not checksums.is_file():
        raise FileNotFoundError(checksums)
    entries = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        entries[name.strip()] = digest
    if relative not in entries:
        raise RuntimeError(f"baseline checksum does not cover {relative}: {run}")
    path = run / relative
    actual = sha256_file(path)
    if actual != entries[relative]:
        raise RuntimeError(f"baseline checksum mismatch: {path}")
    return actual


def _selected_baseline_rows(run: Path, task: str) -> list[dict[str, Any]]:
    relative = "evaluation/final_per_key_metrics.csv"
    _verified_checksum(run, relative)
    rows = []
    for row in read_csv(run / relative):
        beta_ok = task == "forgery" or float(row.get("beta") or 0.0) == 1.5
        if (
            row.get("task") == task and row.get("method") == "proposed"
            and int(row.get("N") or -1) == 25
            and float(row.get("lambda") or -1.0) == 10000.0
            and int(row.get("final_step") or -1) == 150 and beta_ok
        ):
            rows.append(row)
    expected = 2 * 3 * 200
    if len(rows) != expected:
        raise RuntimeError(
            f"expected {expected} ordered-verified {task} baseline rows, found {len(rows)}"
        )
    return rows


def merge_ordered_baseline(
    e2_run: str | Path, forgery_run: str | Path, removal_run: str | Path,
) -> dict[str, Any]:
    root = Path(e2_run)
    config = json.loads(
        (root / "protocol_snapshot/config_resolved.json").read_text(encoding="utf-8")
    )
    e2_rows = read_csv(root / "evaluation/final_per_key_metrics.csv")
    key_ids = {row["key_id"] for row in e2_rows}
    baseline_rows = []
    sources = {"forgery": Path(forgery_run), "removal": Path(removal_run)}
    for task, run in sources.items():
        for row in _selected_baseline_rows(run, task):
            if row["key_id"] not in key_ids:
                continue
            watermark = row["watermark"]
            field = (
                "bit_accuracy_threshold"
                if watermark == "gaussian_shading" else "p_value_threshold"
            )
            threshold = float(config["watermark_runtime"][watermark][field])
            score = float(row["final_score"])
            acceptance = (
                score - threshold if watermark == "gaussian_shading"
                else threshold - score
            )
            baseline_rows.append({
                **row,
                "selection_strategy": "ordered_verified_25_baseline",
                "final_task_margin": acceptance if task == "forgery" else -acceptance,
                "baseline_run": str(run),
            })
    baseline_path = root / "evaluation/e2_ordered_baseline_per_key.csv"
    atomic_csv(baseline_path, baseline_rows)

    comparisons = []
    strategies = sorted({row["selection_strategy"] for row in e2_rows})
    combined = [*e2_rows, *baseline_rows]
    for group_key, group_iter in itertools.groupby(
        sorted(combined, key=lambda row: (
            row["model_setting"], row["watermark"], row["task"],
        )),
        key=lambda row: (
            row["model_setting"], row["watermark"], row["task"],
        ),
    ):
        group = list(group_iter)
        for strategy in strategies:
            for metric, transform in (
                ("success", lambda row: float(str(row["success"]).lower() == "true")),
                ("final_task_margin", None),
            ):
                result = paired_strategy_differences(
                    group, strategy_a=strategy,
                    strategy_b="ordered_verified_25_baseline",
                    metric=metric, transform=transform,
                    seed=derive_seed(
                        "reviewer_selection", *group_key, strategy, "baseline", metric,
                    ),
                )
                comparisons.append({
                    "model_setting": group_key[0], "watermark": group_key[1],
                    "task": group_key[2], **result,
                })
    comparison_path = root / "evaluation/e2_vs_ordered_baseline.csv"
    atomic_csv(comparison_path, comparisons)
    provenance = {
        "status": "COMPLETE",
        "baseline_strategy": "ordered_verified_25_baseline",
        "forgery_run": str(sources["forgery"]),
        "removal_run": str(sources["removal"]),
        "forgery_metrics_sha256": _verified_checksum(
            sources["forgery"], "evaluation/final_per_key_metrics.csv",
        ),
        "removal_metrics_sha256": _verified_checksum(
            sources["removal"], "evaluation/final_per_key_metrics.csv",
        ),
        "e2_metrics_sha256": sha256_file(
            root / "evaluation/final_per_key_metrics.csv"
        ),
        "baseline_row_count": len(baseline_rows),
        "paired_comparison_row_count": len(comparisons),
        "outputs": {
            "baseline_per_key": {
                "path": "evaluation/e2_ordered_baseline_per_key.csv",
                "sha256": sha256_file(baseline_path),
            },
            "paired_comparisons": {
                "path": "evaluation/e2_vs_ordered_baseline.csv",
                "sha256": sha256_file(comparison_path),
            },
        },
    }
    atomic_write_json(root / "evaluation/e2_baseline_provenance.json", provenance)
    return provenance
