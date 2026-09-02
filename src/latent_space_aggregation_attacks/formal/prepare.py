from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.models.loaders import load_target_pipeline
from latent_space_aggregation_attacks.watermarks.base import registered_adapter

from ..core.atomic_io import atomic_write_json, atomic_write_text
from .common import (
    adapter_config, assets_by_name, atomic_csv, atomic_png, bind_run_identity,
    canonical_512, ensure_run_layout, formal_inputs, model_config, open_rgb, png_payload,
    run_identity,
)
from ..core.hashing import sha256_file
from ..core.manifests import write_manifest
from ..core.seeds import configure_torch_determinism, derive_seed

REFERENCE_CONTROL_FIELDS = [
    "protocol_version", "run_id", "model_setting", "watermark", "key_id",
    "candidate_index", "selected_reference_index", "prompt_sha256",
    "generation_seed", "score", "score_name", "accepted", "selected",
    "image_sha256", "image_path",
]
E0_FIELDS = [
    "protocol_version", "run_id", "model_setting", "watermark", "key_id",
    "target_id", "score", "score_name", "accepted", "target_path",
]


def _existing_controls(path: Path) -> list[dict[str, str]]:
    from .common import read_csv
    return read_csv(path) if path.is_file() else []


def _selected_group(
    controls: list[dict[str, Any]], model_setting: str, watermark: str, key_id: str,
) -> list[dict[str, Any]]:
    rows = [
        row for row in controls
        if row["model_setting"] == model_setting
        and row["watermark"] == watermark
        and row["key_id"] == key_id
        and str(row["selected"]).lower() == "true"
    ]
    return sorted(rows, key=lambda row: int(row["selected_reference_index"]))


def prepare_formal_forgery(
    *, config: dict[str, Any], assets_lock: dict[str, Any], run_dir: str | Path,
    run_id: str, key_ids: list[str], project_root: str | Path,
) -> dict[str, Any]:
    """Generate, validate and freeze formal references in a detector-enabled process."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Formal preparation requires a CUDA GPU")
    configure_torch_determinism(torch)
    root = ensure_run_layout(run_dir)
    identity = run_identity(
        config=config, assets_lock=assets_lock, project_root=project_root,
        run_id=run_id, key_ids=key_ids, task="forgery",
    )
    bind_run_identity(root / "manifests/run_manifest.json", identity)
    assets = assets_by_name(assets_lock)
    prompt_by_key, target_by_key, clean_by_key = formal_inputs(assets)
    report_path = root / "preparation_report.json"
    if report_path.is_file():
        import json
        report = json.loads(report_path.read_text(encoding="utf-8"))
        references = _existing_controls(root / "manifests/reference_manifest.csv")
        e0 = _existing_controls(root / "evaluation/e0_original_detection.csv")
        expected_references = (
            len(config["model_settings"]) * len(config["watermarks"]) * len(key_ids)
            * int(config["reference_validity"]["selected_count"])
        )
        expected_e0 = len(config["model_settings"]) * len(config["watermarks"]) * len(key_ids)
        references_valid = len(references) == expected_references and all(
            str(row["accepted"]).lower() == "true"
            and (root / row["image_path"]).is_file()
            and sha256_file(root / row["image_path"]) == row["image_sha256"]
            for row in references
        )
        if references_valid and len(e0) == expected_e0 and report.get("status") == "PREPARATION_COMPLETE":
            return report
    source_config = Path(config["_source_path"])
    protocol_source = Path(project_root) / f"docs/protocols/{PROTOCOL_VERSION}.md"
    shutil.copy2(source_config, root / "protocol_snapshot/source_config.yaml")
    shutil.copy2(protocol_source, root / "protocol_snapshot" / protocol_source.name)
    atomic_write_json(
        root / "protocol_snapshot/config_resolved.json",
        {key: value for key, value in config.items() if not key.startswith("_")},
    )
    atomic_write_text(root / "logs/preparation_command.txt", " ".join(__import__("sys").argv) + "\n")
    atomic_csv(
        root / "manifests/reference_candidate_manifest.csv",
        [row for key_id in key_ids for row in prompt_by_key[key_id]],
    )
    atomic_csv(
        root / "manifests/sample_manifest.csv",
        [target_by_key[key_id] for key_id in key_ids],
    )
    atomic_csv(
        root / "manifests/clean_prior_manifest.csv",
        [row for key_id in key_ids for row in clean_by_key[key_id]],
    )
    write_manifest(root / "manifests/key_manifest.json", {
        "protocol_version": PROTOCOL_VERSION,
        "keys": [
            {
                "key_id": key_id,
                "watermark": watermark,
                "watermark_seed": derive_seed("watermark_key", watermark, key_id),
            }
            for watermark in config["watermarks"] for key_id in key_ids
        ],
    })
    control_path = root / "manifests/reference_selection_control.csv"
    controls: list[dict[str, Any]] = _existing_controls(control_path)
    e0_path = root / "evaluation/e0_original_detection.csv"
    e0_rows: list[dict[str, Any]] = _existing_controls(e0_path)
    candidate_limit = int(config["reference_validity"]["candidate_limit"])
    selected_count = int(config["reference_validity"]["selected_count"])

    for model_setting in config["model_settings"]:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        adapters = {
            watermark: registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            for watermark in config["watermarks"]
        }
        for watermark, adapter in adapters.items():
            for key_id in key_ids:
                key = adapter.create_key({
                    "key_id": key_id,
                    "watermark_seed": derive_seed("watermark_key", watermark, key_id),
                })
                existing_selected = _selected_group(controls, model_setting, watermark, key_id)
                if len(existing_selected) == selected_count and all(
                    (root / row["image_path"]).is_file()
                    and png_payload(open_rgb(root / row["image_path"]))[1] == row["image_sha256"]
                    for row in existing_selected
                ):
                    pass
                else:
                    controls = [
                        row for row in controls
                        if not (
                            row["model_setting"] == model_setting
                            and row["watermark"] == watermark
                            and row["key_id"] == key_id
                        )
                    ]
                    selected_so_far = 0
                    for candidate in prompt_by_key[key_id][:candidate_limit]:
                        candidate_index = int(candidate["reference_index"])
                        generation_seed = derive_seed(
                            "generation", model_setting, watermark, key_id, candidate_index,
                        )
                        image = adapter.generate(candidate["prompt"], key, generation_seed).convert("RGB")
                        detection = adapter.detect(image, key)
                        _, image_hash = png_payload(image)
                        selected = bool(detection.accepted and selected_so_far < selected_count)
                        selected_index: int | str = selected_so_far if selected else ""
                        relative = ""
                        if selected:
                            relative_path = Path("prepared_inputs/references") / model_setting / watermark / key_id / f"ref_{selected_so_far:02d}.png"
                            image_hash = atomic_png(root / relative_path, image)
                            relative = relative_path.as_posix()
                            selected_so_far += 1
                        controls.append({
                            "protocol_version": PROTOCOL_VERSION,
                            "run_id": run_id,
                            "model_setting": model_setting,
                            "watermark": watermark,
                            "key_id": key_id,
                            "candidate_index": candidate_index,
                            "selected_reference_index": selected_index,
                            "prompt_sha256": candidate["prompt_sha256"],
                            "generation_seed": generation_seed,
                            "score": detection.score,
                            "score_name": detection.score_name,
                            "accepted": bool(detection.accepted),
                            "selected": selected,
                            "image_sha256": image_hash,
                            "image_path": relative,
                        })
                        atomic_csv(control_path, controls, REFERENCE_CONTROL_FIELDS)
                        if selected_so_far == selected_count:
                            break
                    if selected_so_far != selected_count:
                        raise RuntimeError(
                            f"Reference gate failed: {model_setting}/{watermark}/{key_id} "
                            f"selected {selected_so_far}/{selected_count} from {candidate_limit}"
                        )
                if not any(
                    row["model_setting"] == model_setting
                    and row["watermark"] == watermark
                    and row["key_id"] == key_id
                    for row in e0_rows
                ):
                    target = target_by_key[key_id]
                    detected = adapter.detect(canonical_512(open_rgb(target["path"])), key)
                    e0_rows.append({
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "model_setting": model_setting,
                        "watermark": watermark,
                        "key_id": key_id,
                        "target_id": target.get("image_id", key_id),
                        "score": detected.score,
                        "score_name": detected.score_name,
                        "accepted": detected.accepted,
                        "target_path": target["path"],
                    })
                    atomic_csv(e0_path, e0_rows, E0_FIELDS)
        del adapters, pipe
        torch.cuda.empty_cache()

    selected = [row for row in controls if str(row["selected"]).lower() == "true"]
    expected = len(config["model_settings"]) * len(config["watermarks"]) * len(key_ids) * selected_count
    if len(selected) != expected or any(str(row["accepted"]).lower() != "true" for row in selected):
        raise RuntimeError(f"Reference manifest has {len(selected)} selected rows; expected {expected}")
    atomic_csv(
        root / "manifests/reference_manifest.csv",
        sorted(selected, key=lambda row: (
            row["model_setting"], row["watermark"], row["key_id"],
            int(row["selected_reference_index"]),
        )),
        REFERENCE_CONTROL_FIELDS,
    )
    expected_e0 = len(config["model_settings"]) * len(config["watermarks"]) * len(key_ids)
    if len(e0_rows) != expected_e0:
        raise RuntimeError(f"E0 has {len(e0_rows)} rows; expected {expected_e0}")
    report = {
        "status": "PREPARATION_COMPLETE",
        "run_id": run_id,
        "key_count": len(key_ids),
        "selected_reference_count": len(selected),
        "e0_row_count": len(e0_rows),
    }
    atomic_write_json(report_path, report)
    return report
