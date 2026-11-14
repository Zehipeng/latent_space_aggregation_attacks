from __future__ import annotations

import json
import io
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..attack import optimize_fixed_budget
from ..core.atomic_io import atomic_write_bytes, atomic_write_json
from ..core.hashing import sha256_file, stable_hash
from ..core.resume import ResumeState, load_resume_state, save_resume_state
from ..core.seeds import (
    capture_rng_state, configure_torch_determinism, derive_seed,
    restore_rng_state, seed_runtime,
)
from ..formal.attack import _encode, _image_tensor, _tensor_pil
from ..formal.common import (
    assets_by_name, atomic_csv, atomic_png, canonical_512, formal_inputs,
    model_config, open_rgb, read_csv,
)
from ..latent_targets import forgery_target, fp32_mean, removal_target
from ..models.loaders import load_proxy_vae
from . import MODEL_ORDER, PROTOCOL_VERSION, WATERMARK_ORDER
from .conditions import condition_registry, validate_registry


def _progress(root: Path, completed: int, total: int, started: float) -> None:
    elapsed = time.perf_counter() - started
    per = elapsed / completed if completed else 0.0
    remaining = total - completed
    atomic_write_json(root / "progress.json", {
        "stage": "attack", "completed_units": completed, "total_units": total,
        "remaining_units": remaining, "estimated_remaining_seconds": per * remaining,
        "estimated_completion_utc": (
            datetime.now(timezone.utc) + timedelta(seconds=per * remaining)
        ).isoformat(),
    })


def _source(root: Path, path: str) -> Any:
    value = Path(path)
    return open_rgb(value if value.is_absolute() else root / value)


def _distance(first: Any, second: Any) -> float:
    return float((first.float() - second.float()).square().mean().sqrt().item())


def _cosine(first: Any, second: Any) -> float:
    import torch.nn.functional as functional
    a, b = first.float().flatten(), second.float().flatten()
    return float(functional.cosine_similarity(a, b, dim=0).item())


def _group_rows(
    rows: list[dict[str, str]], fields: tuple[str, ...],
) -> dict[tuple[str, ...], list[dict[str, str]]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[field] for field in fields), []).append(row)
    return grouped


def attack(
    config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
    key_ids: list[str], git_sha: str,
) -> dict[str, Any]:
    """Run fixed-budget attacks without importing or querying a detector."""
    import torch

    report_path = root / "attack_report.json"
    if report_path.is_file() and any(
        (root / name).is_file()
        for name in ("smoke_report.json", "evaluation_report.json")
    ):
        return json.loads(report_path.read_text(encoding="utf-8"))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch)
    started = time.perf_counter()
    assets = assets_by_name(lock)
    _, _, clean = formal_inputs(assets)
    conditions = condition_registry()
    validate_registry(conditions)
    selections = _group_rows(
        read_csv(root / "manifests/reference_selection_manifest.csv"),
        ("model_setting", "watermark", "key_id", "selection_strategy"),
    )
    sources = {
        (row["model_setting"], row["watermark"], row["task"], row["key_id"]): row
        for row in read_csv(root / "manifests/common_source_manifest.csv")
    }
    shuffled = {
        row["key_id"]: row["shuffled_key_id"]
        for row in read_csv(root / "manifests/shuffled_key_control.csv")
    }
    subset_rows = _group_rows(
        read_csv(root / "manifests/clean_subset_manifest.csv"),
        ("model_setting", "watermark", "key_id", "subset_seed"),
    )
    records_dir = root / "manifests/attack_units"
    mechanism_dir = root / "evaluation/mechanism_latent_units"
    control_dir = root / "evaluation/direction_control_units"
    for directory in (records_dir, mechanism_dir, control_dir):
        directory.mkdir(parents=True, exist_ok=True)

    eligible = {
        (model, watermark, key_id, strategy)
        for model, watermark, key_id, strategy in selections
    }
    total = sum(
        (condition.model_setting, condition.watermark, key_id,
         condition.selection_strategy) in eligible
        for condition in conditions for key_id in key_ids
    )
    completed = 0
    peak = int(torch.cuda.max_memory_reserved())

    for model_setting in MODEL_ORDER:
        vae = load_proxy_vae(model_config(assets, model_setting), offline=True)
        device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
        for watermark in WATERMARK_ORDER:
            applicable = [
                condition for condition in conditions
                if condition.model_setting == model_setting
                and condition.watermark == watermark
            ]
            strategies = sorted({condition.selection_strategy for condition in applicable})
            for key_id in key_ids:
                clean_rows = clean[key_id]
                clean_images = [canonical_512(open_rgb(row["path"])) for row in clean_rows]
                clean_latents = _encode(
                    vae, clean_images, batch_size=int(config["reference_encode_batch_size"]),
                ).float()
                clean_centroid = fp32_mean(
                    clean_latents[:int(config["clean_reference_count"])]
                )

                for strategy in strategies:
                    selection_key = (model_setting, watermark, key_id, strategy)
                    if selection_key not in selections:
                        continue
                    selected_rows = sorted(
                        selections[selection_key], key=lambda row: int(row["selected_rank"]),
                    )
                    other_key = shuffled[key_id]
                    shuffled_rows = sorted(
                        selections[(model_setting, watermark, other_key, strategy)],
                        key=lambda row: int(row["selected_rank"]),
                    )
                    if len(selected_rows) != 25 or len(shuffled_rows) != 25:
                        raise RuntimeError("eligible reference selection must contain 25 rows")
                    for row in selected_rows + shuffled_rows:
                        path = root / row["image_path"]
                        if sha256_file(path) != row["image_sha256"]:
                            raise RuntimeError(f"selected reference SHA mismatch: {path}")
                    selected_latents = _encode(
                        vae, [open_rgb(root / row["image_path"]) for row in selected_rows],
                        batch_size=int(config["reference_encode_batch_size"]),
                    ).float()
                    shuffled_latents = _encode(
                        vae, [open_rgb(root / row["image_path"]) for row in shuffled_rows],
                        batch_size=int(config["reference_encode_batch_size"]),
                    ).float()
                    same_centroid = fp32_mean(selected_latents)
                    shuffled_centroid = fp32_mean(shuffled_latents)

                    subset_centroids: dict[str, Any] = {}
                    for subset_seed in config["clean_subset_seeds"]:
                        rows = sorted(
                            subset_rows[(model_setting, watermark, key_id, str(subset_seed))],
                            key=lambda row: int(row["selected_rank"]),
                        )
                        indices = [int(row["clean_index"]) for row in rows]
                        subset_centroids[str(subset_seed)] = fp32_mean(clean_latents[indices])
                    main_direction = same_centroid - clean_centroid
                    directions = {
                        seed: same_centroid - centroid
                        for seed, centroid in subset_centroids.items()
                    }
                    control_path = control_dir / f"{stable_hash('|'.join(selection_key))}.json"
                    centroid_relative = (
                        Path("evaluation_spool/centroids") /
                        f"{stable_hash('|'.join(selection_key))}.pt"
                    )
                    if not (root / centroid_relative).is_file():
                        payload = io.BytesIO()
                        torch.save({
                            "selection_key": selection_key,
                            "same_key_centroid": same_centroid.detach().float().cpu(),
                            "shuffled_key_centroid": shuffled_centroid.detach().float().cpu(),
                        }, payload)
                        atomic_write_bytes(root / centroid_relative, payload.getvalue())
                    if not control_path.is_file():
                        atomic_write_json(control_path, {
                            "model_setting": model_setting, "watermark": watermark,
                            "key_id": key_id, "selection_strategy": strategy,
                            "same_key_centroid_norm": float(same_centroid.float().norm().item()),
                            "shuffled_key_id": other_key,
                            "distance_same_to_shuffled": _distance(
                                same_centroid, shuffled_centroid,
                            ),
                            "clean_centroid_norm": float(clean_centroid.float().norm().item()),
                            "main_direction_norm": float(main_direction.float().norm().item()),
                            "centroid_tensor_path": centroid_relative.as_posix(),
                            "subset_direction_controls": [
                                {
                                    "subset_seed": seed,
                                    "direction_norm": float(direction.float().norm().item()),
                                    "cosine_to_main": _cosine(direction, main_direction),
                                }
                                for seed, direction in sorted(directions.items())
                            ],
                            "pairwise_subset_cosines": [
                                {"first_seed": first, "second_seed": second,
                                 "cosine": _cosine(directions[first], directions[second])}
                                for index, first in enumerate(sorted(directions))
                                for second in sorted(directions)[index + 1:]
                            ],
                        })

                    for condition in [
                        value for value in applicable
                        if value.selection_strategy == strategy
                    ]:
                        unit = condition.id + "|" + key_id
                        record_path = records_dir / f"{stable_hash(unit)}.json"
                        if record_path.is_file():
                            record = json.loads(record_path.read_text(encoding="utf-8"))
                            output = root / record["output_image_path"]
                            if output.is_file() and sha256_file(output) == record["output_sha256"]:
                                completed += 1
                                continue

                        source_row = sources[(model_setting, watermark, condition.task, key_id)]
                        source_image = _source(root, source_row["source_path"])
                        if condition.task == "forgery":
                            source_image = canonical_512(source_image)
                        source_tensor = _image_tensor(source_image, device=device, dtype=dtype)
                        source_latent = _encode(vae, [source_image], batch_size=1).float()
                        target = (
                            forgery_target(selected_latents)
                            if condition.task == "forgery"
                            else removal_target(
                                source_latent, selected_latents,
                                clean_latents[:int(condition.N_clean)],
                                float(condition.beta),
                            )
                        )
                        input_hash = stable_hash({
                            "condition": condition.id, "key_id": key_id,
                            "source": source_row["source_sha256"],
                            "references": [row["image_sha256"] for row in selected_rows],
                            "shuffled_references": [row["image_sha256"] for row in shuffled_rows],
                            "clean": [sha256_file(row["path"]) for row in clean_rows],
                        })
                        state_path = root / "resume_state" / f"{stable_hash(unit)}.pkl"
                        step, current, history, prior = 0, source_tensor, [], 0.0
                        seed = derive_seed("worker", PROTOCOL_VERSION, condition.id, key_id)
                        seed_runtime(seed, torch)
                        if state_path.is_file():
                            state = load_resume_state(
                                state_path, expected_unit_id=unit, input_hash=input_hash,
                                resolved_config_hash=config["resolved_config_hash"],
                                protocol_version=PROTOCOL_VERSION, git_sha=git_sha,
                            )
                            step, current, history = state.step, state.image_tensor, state.loss_history
                            prior = float(state.timing["optimization_compute_time"])
                            restore_rng_state(state.rng_state, torch)

                        unit_started = time.perf_counter()

                        def persist_checkpoint(
                            at: int, image: Any, losses: list[dict[str, Any]],
                        ) -> None:
                            elapsed = prior + time.perf_counter() - unit_started
                            save_resume_state(state_path, ResumeState(
                                unit_id=unit, step=at, image_tensor=image.detach().cpu(),
                                loss_history=losses, rng_state=capture_rng_state(torch),
                                timing={"optimization_compute_time": elapsed},
                                input_hash=input_hash,
                                resolved_config_hash=config["resolved_config_hash"],
                                protocol_version=PROTOCOL_VERSION, git_sha=git_sha,
                            ))
                            relative = (
                                Path("evaluation_spool/checkpoints") / stable_hash(unit) /
                                f"step_{at:03d}.png"
                            )
                            digest = atomic_png(root / relative, _tensor_pil(image))
                            with torch.inference_mode():
                                latent = vae.encode(
                                    image.to(device=device, dtype=dtype)
                                ).latent_dist.mode() * (1.0 / float(vae.config.scaling_factor))
                            atomic_write_json(
                                mechanism_dir / f"{stable_hash(unit + '|' + str(at))}.json",
                                {
                                    "unit_id": unit, "condition_id": condition.id,
                                    "model_setting": model_setting, "watermark": watermark,
                                    "task": condition.task, "key_id": key_id,
                                    "selection_strategy": strategy, "step": at,
                                    "checkpoint_image_path": relative.as_posix(),
                                    "checkpoint_sha256": digest,
                                    "distance_to_target": _distance(latent, target),
                                    "distance_to_same_key_centroid": _distance(
                                        latent, same_centroid,
                                    ),
                                    "distance_to_shuffled_key_centroid": _distance(
                                        latent, shuffled_centroid,
                                    ),
                                    "distance_to_clean_centroid": _distance(
                                        latent, clean_centroid,
                                    ),
                                },
                            )

                        checkpoint_zero = mechanism_dir / f"{stable_hash(unit + '|0')}.json"
                        if step == 0 and not checkpoint_zero.is_file():
                            persist_checkpoint(0, source_tensor, history)
                        elif step > 0:
                            required = (0,) + tuple(
                                value for value in (50, 100, 150) if value <= step
                            )
                            if any(
                                not (mechanism_dir / f"{stable_hash(unit + '|' + str(value))}.json").is_file()
                                for value in required
                            ):
                                raise RuntimeError(
                                    f"resume state exists without complete mechanism checkpoints: {unit}"
                                )

                        if step < int(config["steps"]):
                            result = optimize_fixed_budget(
                                source_tensor, target, vae,
                                lambda_pixel=float(condition.lambda_pixel),
                                learning_rate=float(config["learning_rate"]),
                                final_step=int(config["steps"]), start_step=step,
                                current_image=current, original_image=source_tensor,
                                history=history, checkpoint_callback=persist_checkpoint,
                                checkpoint_every=int(config["resume_every"]),
                            )
                            current = result.image
                            elapsed = prior + result.optimization_compute_time
                        else:
                            elapsed = prior

                        relative = Path("evaluation_spool/attacks") / condition.id / f"{key_id}.png"
                        digest = atomic_png(root / relative, _tensor_pil(current))
                        record = {
                            "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                            "condition_id": condition.id,
                            "selection_strategy": strategy,
                            "watermark": watermark, "task": condition.task,
                            "key_id": key_id, "model_setting": model_setting,
                            "N_watermarked": condition.N_watermarked,
                            "N_clean": condition.N_clean,
                            "beta": condition.beta,
                            "lambda_pixel": condition.lambda_pixel,
                            "seed": seed, "final_step": config["steps"],
                            "optimization_compute_time": elapsed,
                            "input_hash": input_hash,
                            "output_image_path": relative.as_posix(),
                            "output_sha256": digest,
                            "source_path": source_row["source_path"],
                            "source_id": source_row["source_id"],
                            "reference_ids": ";".join(
                                row["image_sha256"] for row in selected_rows
                            ),
                            "clean_ids": ";".join(
                                row.get("image_id", row["path"])
                                for row in clean_rows[:int(condition.N_clean)]
                            ),
                        }
                        atomic_write_json(record_path, record)
                        completed += 1
                        peak = max(peak, int(torch.cuda.max_memory_reserved()))
                        _progress(root, completed, total, started)
            torch.cuda.empty_cache()
        vae = None
        torch.cuda.empty_cache()

    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(records_dir.glob("*.json"))
    ]
    if len(rows) != total:
        raise RuntimeError(f"expected {total} attack rows, found {len(rows)}")
    atomic_csv(root / "manifests/attack_outputs.csv", rows)
    mechanism = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(mechanism_dir.glob("*.json"))
    ]
    if len(mechanism) != total * 4:
        raise RuntimeError(f"expected {total * 4} mechanism checkpoints, found {len(mechanism)}")
    atomic_csv(root / "evaluation/mechanism_latent_trajectory.csv", mechanism)
    controls = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(control_dir.glob("*.json"))
    ]
    atomic_write_json(root / "evaluation/direction_controls.json", controls)
    report = {
        "status": "ATTACK_COMPLETE", "protocol_version": PROTOCOL_VERSION,
        "condition_count": len(conditions), "eligible_output_count": len(rows),
        "mechanism_checkpoint_count": len(mechanism),
        "elapsed_seconds": time.perf_counter() - started,
        "gpu_peak_reserved_bytes": peak,
        "gpu_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__, "torch_cuda_version": torch.version.cuda,
    }
    atomic_write_json(report_path, report)
    return report
