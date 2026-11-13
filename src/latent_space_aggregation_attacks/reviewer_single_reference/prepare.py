from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from ..core.atomic_io import atomic_write_json
from ..core.manifests import write_manifest
from ..core.seeds import configure_torch_determinism, derive_seed
from ..formal.common import (
    adapter_config, assets_by_name, atomic_csv, atomic_png, canonical_512,
    formal_inputs, model_config, open_rgb,
)
from ..models.loaders import load_target_pipeline
from ..watermarks.base import registered_adapter
from . import MODEL_ORDER, PROTOCOL_VERSION, TASK_ORDER, WATERMARK_ORDER
from .common import bind_identity, identity, layout


def prepare(
    config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
    key_ids: list[str], project: Path,
) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    started = time.perf_counter()
    configure_torch_determinism(torch)
    layout(root)
    ident = identity(config, lock, project, run_id, key_ids)
    bind_identity(root / "manifests/run_manifest.json", ident)
    report_path = root / "preparation_report.json"
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))

    shutil.copy2(config["_source_path"], root / "protocol_snapshot/source_config.yaml")
    shutil.copy2(
        project / "docs/protocols/reviewer_single_reference_v1.0.md",
        root / "protocol_snapshot/reviewer_single_reference_v1.0.md",
    )
    atomic_write_json(
        root / "protocol_snapshot/config_resolved.json",
        {key: value for key, value in config.items() if not key.startswith("_")},
    )
    atomic_write_json(root / "protocol_snapshot/assets.lock.json", lock)

    assets = assets_by_name(lock)
    prompts, _, clean = formal_inputs(assets)
    clean_rows = [row for key_id in key_ids for row in clean[key_id][:25]]
    if len(clean_rows) != len(key_ids) * 25:
        raise RuntimeError("25-image clean-prior manifest is incomplete")
    clean_paths = [row["path"] for row in clean_rows]
    if len(set(clean_paths)) != len(clean_paths):
        raise RuntimeError("25-image clean-prior groups must be disjoint across keys")
    atomic_csv(root / "manifests/clean_prior_manifest.csv", clean_rows)
    atomic_csv(
        root / "manifests/reference_candidate_manifest.csv",
        [row for key_id in key_ids for row in prompts[key_id]],
    )
    write_manifest(root / "manifests/key_manifest.json", {
        "protocol_version": PROTOCOL_VERSION,
        "keys": [
            {
                "watermark": watermark,
                "key_id": key_id,
                "watermark_seed": derive_seed("watermark_key", watermark, key_id),
            }
            for watermark in WATERMARK_ORDER
            for key_id in key_ids
        ],
    })

    reference_rows: list[dict[str, Any]] = []
    detection_rows: list[dict[str, Any]] = []
    control_rows: list[dict[str, Any]] = []
    for model_setting in MODEL_ORDER:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in WATERMARK_ORDER:
            adapter = registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            for key_id in key_ids:
                key = adapter.create_key({
                    "key_id": key_id,
                    "watermark_seed": derive_seed("watermark_key", watermark, key_id),
                })
                chosen: dict[str, Any] | None = None
                for candidate in prompts[key_id][:int(config["candidate_limit"])]:
                    candidate_index = int(candidate["reference_index"])
                    seed = derive_seed(
                        "generation", model_setting, watermark, key_id, candidate_index,
                    )
                    image = adapter.generate(candidate["prompt"], key, seed).convert("RGB")
                    detected = adapter.detect(image, key)
                    selected = bool(detected.accepted and chosen is None)
                    control_rows.append({
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "model_setting": model_setting,
                        "watermark": watermark,
                        "key_id": key_id,
                        "candidate_index": candidate_index,
                        "generation_seed": seed,
                        "prompt_sha256": candidate["prompt_sha256"],
                        "score": detected.score,
                        "score_name": detected.score_name,
                        "accepted": detected.accepted,
                        "selected": selected,
                    })
                    if selected:
                        relative = (
                            Path("prepared_inputs/references") / model_setting /
                            watermark / f"{key_id}.png"
                        )
                        digest = atomic_png(root / relative, image)
                        chosen = {
                            "protocol_version": PROTOCOL_VERSION,
                            "run_id": run_id,
                            "model_setting": model_setting,
                            "watermark": watermark,
                            "key_id": key_id,
                            "candidate_index": candidate_index,
                            "generation_seed": seed,
                            "prompt_sha256": candidate["prompt_sha256"],
                            "image_path": relative.as_posix(),
                            "image_sha256": digest,
                            "score": detected.score,
                            "score_name": detected.score_name,
                            "accepted": True,
                        }
                        break
                if chosen is None:
                    raise RuntimeError(
                        f"no accepted reference: {model_setting}/{watermark}/{key_id}"
                    )
                reference_rows.append(chosen)
                clean_source = canonical_512(open_rgb(clean[key_id][0]["path"]))
                clean_detected = adapter.detect(clean_source, key)
                for task, score, name, accepted, source in (
                    ("removal", chosen["score"], chosen["score_name"], True, chosen["image_path"]),
                    ("forgery", clean_detected.score, clean_detected.score_name,
                     clean_detected.accepted, clean[key_id][0]["path"]),
                ):
                    detection_rows.append({
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "model_setting": model_setting,
                        "watermark": watermark,
                        "task": task,
                        "key_id": key_id,
                        "initial_score": score,
                        "score_name": name,
                        "accepted_before": accepted,
                        "source_path": source,
                    })
            del adapter
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()

    atomic_csv(root / "manifests/reference_manifest.csv", reference_rows)
    atomic_csv(root / "manifests/reference_selection_control.csv", control_rows)
    atomic_csv(root / "manifests/sample_manifest.csv", [
        {
            "model_setting": model_setting,
            "watermark": watermark,
            "key_id": key_id,
            "removal_source": next(
                row["image_path"] for row in reference_rows
                if row["model_setting"] == model_setting
                and row["watermark"] == watermark
                and row["key_id"] == key_id
            ),
            "forgery_source": clean[key_id][0]["path"],
            "clean_ids": "|".join(
                row.get("image_id", row["path"]) for row in clean[key_id][:25]
            ),
        }
        for model_setting in MODEL_ORDER
        for watermark in WATERMARK_ORDER
        for key_id in key_ids
    ])
    atomic_csv(root / "evaluation/original_detection.csv", detection_rows)
    report = {
        "status": "PREPARATION_COMPLETE",
        "protocol_version": PROTOCOL_VERSION,
        "reference_count": len(reference_rows),
        "clean_count": len(clean_rows),
        "detection_count": len(detection_rows),
        "elapsed_seconds": time.perf_counter() - started,
        "model_order": list(MODEL_ORDER),
        "watermark_order": list(WATERMARK_ORDER),
        "task_order": list(TASK_ORDER),
    }
    atomic_write_json(report_path, report)
    return report
