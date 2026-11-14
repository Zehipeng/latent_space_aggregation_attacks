from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file
from ..core.manifests import write_manifest
from ..core.seeds import configure_torch_determinism, derive_seed
from ..formal.common import (
    adapter_config, assets_by_name, atomic_csv, atomic_png, canonical_512,
    formal_inputs, model_config, open_rgb, read_csv,
)
from ..models.loaders import load_target_pipeline
from ..watermarks.base import registered_adapter
from . import MODEL_ORDER, PROTOCOL_VERSION, WATERMARK_ORDER
from .common import bind_identity, identity, layout
from .strategies import (
    clean_subsets, pool_feasibility, select_references, shuffled_key,
    strategy_registry,
)


def _preparation_progress(
    root: Path, completed: int, total: int, started: float,
    *, model_setting: str, watermark: str, key_id: str,
) -> None:
    elapsed = time.perf_counter() - started
    per = elapsed / completed if completed else 0.0
    remaining = total - completed
    atomic_write_json(root / "progress.json", {
        "stage": "prepare_candidate_bank",
        "completed_groups": completed, "total_groups": total,
        "completed_candidates": completed * 64,
        "total_candidates": total * 64,
        "remaining_groups": remaining,
        "current_model_setting": model_setting,
        "current_watermark": watermark, "current_key_id": key_id,
        "estimated_remaining_seconds": per * remaining,
        "estimated_completion_utc": (
            datetime.now(timezone.utc) + timedelta(seconds=per * remaining)
        ).isoformat(),
    })


def _valid_group(path: Path, root: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    rows = read_csv(path)
    if len(rows) != 64:
        return None
    for row in rows:
        image = root / row["image_path"]
        if not image.is_file() or sha256_file(image) != row["image_sha256"]:
            return None
    return rows


def prepare(
    config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
    key_ids: list[str], project: Path,
) -> dict[str, Any]:
    """Generate the complete candidate bank and freeze detector-blind selections."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch)
    started = time.perf_counter()
    layout(root)
    ident = identity(config, lock, project, run_id, key_ids)
    bind_identity(root / "manifests/run_manifest.json", ident)
    report_path = root / "preparation_report.json"
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))

    shutil.copy2(config["_source_path"], root / "protocol_snapshot/source_config.yaml")
    shutil.copy2(
        project / "docs/protocols/reviewer_selection_mechanism_v1.0.md",
        root / "protocol_snapshot/reviewer_selection_mechanism_v1.0.md",
    )
    atomic_write_json(
        root / "protocol_snapshot/config_resolved.json",
        {key: value for key, value in config.items() if not key.startswith("_")},
    )
    atomic_write_json(root / "protocol_snapshot/assets.lock.json", lock)

    assets = assets_by_name(lock)
    prompts, targets, clean = formal_inputs(assets)
    clean_rows = [row for key_id in key_ids for row in clean[key_id]]
    if len(clean_rows) != len(key_ids) * 25:
        raise RuntimeError("25-image clean-prior manifest is incomplete")
    atomic_csv(root / "manifests/clean_prior_manifest.csv", clean_rows)
    write_manifest(root / "manifests/key_manifest.json", {
        "protocol_version": PROTOCOL_VERSION,
        "keys": [
            {
                "watermark": watermark,
                "key_id": key_id,
                "watermark_seed": derive_seed("watermark_key", watermark, key_id),
            }
            for watermark in WATERMARK_ORDER for key_id in key_ids
        ],
    })

    candidate_rows: list[dict[str, Any]] = []
    group_dir = root / "manifests/candidate_bank_units"
    group_dir.mkdir(parents=True, exist_ok=True)
    completed_groups = 0
    total_groups = len(MODEL_ORDER) * len(WATERMARK_ORDER) * len(key_ids)
    for model_setting in MODEL_ORDER:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in WATERMARK_ORDER:
            adapter = registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            for key_id in key_ids:
                group_path = group_dir / f"{model_setting}__{watermark}__{key_id}.csv"
                existing = _valid_group(group_path, root)
                if existing is not None:
                    candidate_rows.extend(existing)
                    completed_groups += 1
                    _preparation_progress(
                        root, completed_groups, total_groups, started,
                        model_setting=model_setting, watermark=watermark,
                        key_id=key_id,
                    )
                    continue
                key = adapter.create_key({
                    "key_id": key_id,
                    "watermark_seed": derive_seed("watermark_key", watermark, key_id),
                })
                rows = []
                for candidate in prompts[key_id][:64]:
                    index = int(candidate["reference_index"])
                    seed = derive_seed(
                        "generation", model_setting, watermark, key_id, index,
                    )
                    image = adapter.generate(candidate["prompt"], key, seed).convert("RGB")
                    detected = adapter.detect(image, key)
                    relative = (
                        Path("prepared_inputs/candidate_bank") / model_setting /
                        watermark / key_id / f"candidate_{index:02d}.png"
                    )
                    digest = atomic_png(root / relative, image)
                    rows.append({
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "model_setting": model_setting,
                        "watermark": watermark,
                        "key_id": key_id,
                        "candidate_index": index,
                        "generation_seed": seed,
                        "prompt_sha256": candidate["prompt_sha256"],
                        "image_path": relative.as_posix(),
                        "image_sha256": digest,
                        "score": detected.score,
                        "score_name": detected.score_name,
                        "accepted": bool(detected.accepted),
                    })
                atomic_csv(group_path, rows)
                candidate_rows.extend(rows)
                completed_groups += 1
                _preparation_progress(
                    root, completed_groups, total_groups, started,
                    model_setting=model_setting, watermark=watermark,
                    key_id=key_id,
                )
            del adapter
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()

    expected_candidates = len(MODEL_ORDER) * len(WATERMARK_ORDER) * len(key_ids) * 64
    if len(candidate_rows) != expected_candidates:
        raise RuntimeError(
            f"expected {expected_candidates} candidates, found {len(candidate_rows)}"
        )
    candidate_rows.sort(key=lambda row: (
        row["model_setting"], row["watermark"], row["key_id"],
        int(row["candidate_index"]),
    ))
    atomic_csv(root / "manifests/candidate_bank_manifest.csv", candidate_rows)

    grouped = {
        (model, watermark, key_id): [
            row for row in candidate_rows
            if row["model_setting"] == model and row["watermark"] == watermark
            and row["key_id"] == key_id
        ]
        for model in MODEL_ORDER for watermark in WATERMARK_ORDER for key_id in key_ids
    }
    selection_rows: list[dict[str, Any]] = []
    ineligible_rows: list[dict[str, Any]] = []
    feasibility_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    original_detection: list[dict[str, Any]] = []
    clean_subset_rows: list[dict[str, Any]] = []

    # Re-open detector adapters only for the two common sources per tuple. The
    # selection manifest written below deliberately contains no detector field.
    for model_setting in MODEL_ORDER:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in WATERMARK_ORDER:
            adapter = registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            for key_id in key_ids:
                bank = grouped[(model_setting, watermark, key_id)]
                feasibility = pool_feasibility(bank)
                feasibility_rows.append({
                    "model_setting": model_setting, "watermark": watermark,
                    "key_id": key_id,
                    **{f"accepted_25_within_{prefix}": value
                       for prefix, value in feasibility.items()},
                    "accepted_total": sum(str(row["accepted"]).lower() == "true" for row in bank),
                })
                for strategy in strategy_registry():
                    try:
                        selected = select_references(
                            bank, strategy, model_setting=model_setting,
                            watermark=watermark, key_id=key_id,
                        )
                    except ValueError as exc:
                        ineligible_rows.append({
                            "model_setting": model_setting, "watermark": watermark,
                            "key_id": key_id, "selection_strategy": strategy.id,
                            "reason": str(exc),
                        })
                        continue
                    for rank, row in enumerate(selected):
                        selection_rows.append({
                            "protocol_version": PROTOCOL_VERSION,
                            "run_id": run_id,
                            "model_setting": model_setting,
                            "watermark": watermark,
                            "key_id": key_id,
                            "selection_strategy": strategy.id,
                            "selected_rank": rank,
                            "candidate_index": int(row["candidate_index"]),
                            "image_path": row["image_path"],
                            "image_sha256": row["image_sha256"],
                        })

                accepted = [row for row in bank if str(row["accepted"]).lower() == "true"]
                if not accepted:
                    raise RuntimeError(
                        f"no accepted common removal source for {model_setting}/{watermark}/{key_id}"
                    )
                removal = accepted[0]
                forgery = targets[key_id]
                key = adapter.create_key({
                    "key_id": key_id,
                    "watermark_seed": derive_seed("watermark_key", watermark, key_id),
                })
                for task, source_path, source_sha in (
                    ("removal", root / removal["image_path"], removal["image_sha256"]),
                    ("forgery", Path(forgery["path"]), sha256_file(forgery["path"])),
                ):
                    source = open_rgb(source_path)
                    if task == "forgery":
                        source = canonical_512(source)
                    detected = adapter.detect(source, key)
                    source_rows.append({
                        "model_setting": model_setting, "watermark": watermark,
                        "task": task, "key_id": key_id,
                        "source_path": (
                            removal["image_path"] if task == "removal" else forgery["path"]
                        ),
                        "source_sha256": source_sha,
                        "source_id": (
                            removal["image_sha256"] if task == "removal"
                            else forgery.get("image_id", key_id)
                        ),
                    })
                    original_detection.append({
                        "model_setting": model_setting, "watermark": watermark,
                        "task": task, "key_id": key_id,
                        "initial_score": detected.score,
                        "score_name": detected.score_name,
                        "accepted_before": bool(detected.accepted),
                    })

                clean_bank = [
                    {**row, "clean_index": int(row["clean_index"])}
                    for row in clean[key_id]
                ]
                for subset_seed, subset in clean_subsets(
                    clean_bank, model_setting=model_setting,
                    watermark=watermark, key_id=key_id,
                ).items():
                    for rank, row in enumerate(subset):
                        clean_subset_rows.append({
                            "model_setting": model_setting, "watermark": watermark,
                            "key_id": key_id, "subset_seed": subset_seed,
                            "selected_rank": rank, "clean_index": row["clean_index"],
                            "path": row["path"],
                            "image_id": row.get("image_id", row["path"]),
                        })
            del adapter
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()

    atomic_csv(root / "manifests/reference_selection_manifest.csv", selection_rows)
    atomic_csv(
        root / "manifests/ineligible_selection_groups.csv", ineligible_rows,
        ["model_setting", "watermark", "key_id", "selection_strategy", "reason"],
    )
    atomic_csv(root / "manifests/pool_feasibility.csv", feasibility_rows)
    atomic_csv(root / "manifests/common_source_manifest.csv", source_rows)
    atomic_csv(root / "evaluation/original_detection.csv", original_detection)
    atomic_csv(root / "manifests/clean_subset_manifest.csv", clean_subset_rows)
    atomic_csv(root / "manifests/shuffled_key_control.csv", [
        {"key_id": key_id, "shuffled_key_id": shuffled_key(key_id, key_ids)}
        for key_id in key_ids
    ])

    report = {
        "status": "PREPARATION_COMPLETE",
        "protocol_version": PROTOCOL_VERSION,
        "candidate_count": len(candidate_rows),
        "selected_reference_rows": len(selection_rows),
        "eligible_selection_groups": len(selection_rows) // 25,
        "ineligible_selection_groups": len(ineligible_rows),
        "common_source_count": len(source_rows),
        "elapsed_seconds": time.perf_counter() - started,
    }
    atomic_write_json(report_path, report)
    return report
