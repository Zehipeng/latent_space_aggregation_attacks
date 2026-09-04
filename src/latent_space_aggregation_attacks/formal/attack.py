from __future__ import annotations

import io
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.methods.baselines.jain import (
    jain_forgery_target, jain_removal_mean_image,
)
from latent_space_aggregation_attacks.methods.baselines.distortions import apply_distortion
from latent_space_aggregation_attacks.methods.baselines.simple_averaging import (
    apply_pixel_direction, estimate_pixel_direction,
)
from latent_space_aggregation_attacks.attack import (
    optimize_fixed_budget, optimize_fixed_budget_batch,
)
from latent_space_aggregation_attacks.latent_targets import forgery_target, removal_target
from latent_space_aggregation_attacks.models.loaders import load_proxy_vae

from ..core.atomic_io import atomic_write_bytes, atomic_write_json, atomic_write_text
from ..core.conditions import conditions_for_task
from .common import (
    assets_by_name, atomic_csv, atomic_png, canonical_512, ensure_run_layout, formal_inputs,
    git_sha, model_config, open_rgb, read_csv,
)
from ..core.hashing import sha256_file, stable_hash
from ..core.ledger import LedgerEvent, append_event
from ..core.locking import UnitLock
from ..core.resume import ResumeState, load_resume_state, save_resume_state
from ..core.seeds import (
    capture_rng_state, configure_torch_determinism, derive_seed, restore_rng_state,
    seed_runtime,
)

ATTACK_FIELDS = [
    "protocol_version", "run_id", "condition_id", "experiment", "task",
    "watermark", "model_setting", "method", "key_id", "target_id",
    "reference_ids", "clean_ids", "N", "lambda", "beta", "gamma", "seed",
    "final_step", "optimization_compute_time", "unit_wall_time", "input_hash", "output_sha256",
    "output_image_path", "control_parent_condition_id", "matched_parent_l2_preclip",
    "matched_control_l2_postclip", "matched_control_linf_postclip",
]


def _write_attack_progress(root: Path, rows: list[dict[str, Any]], total: int) -> None:
    durations = sorted(float(row["unit_wall_time"]) for row in rows[-100:])
    rolling = durations[len(durations) // 2] if durations else 0.0
    remaining = max(0, total - len(rows))
    now = datetime.now(timezone.utc)
    atomic_write_json(root / "progress.json", {
        "stage": "attack", "completed_units": len(rows), "total_units": total,
        "remaining_units": remaining, "rolling_median_seconds_per_unit": rolling,
        "estimated_remaining_seconds": rolling * remaining,
        "estimated_completion_utc": (now + timedelta(seconds=rolling * remaining)).isoformat(),
        "updated_at_utc": now.isoformat(),
    })


def _image_tensor(image: Any, *, device: Any, dtype: Any) -> Any:
    import numpy as np
    import torch
    from PIL import Image
    rgb = image.convert("RGB")
    scale = 512 / min(rgb.size)
    resized = rgb.resize((round(rgb.width * scale), round(rgb.height * scale)), Image.Resampling.BICUBIC)
    left, top = (resized.width - 512) // 2, (resized.height - 512) // 2
    array = np.asarray(resized.crop((left, top, left + 512, top + 512)), dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=dtype)


def _tensor_pil(image: Any) -> Any:
    import numpy as np
    from PIL import Image
    value = image.detach().float().clamp(-1.0, 1.0)
    if value.ndim == 4:
        value = value[0]
    array = ((value.permute(1, 2, 0).cpu().numpy() + 1) * 127.5).round().clip(0, 255)
    return Image.fromarray(array.astype(np.uint8), mode="RGB")


def _encode(vae: Any, images: list[Any], *, batch_size: int) -> Any:
    import torch
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    latents = []
    with torch.inference_mode():
        for offset in range(0, len(images), batch_size):
            tensor = torch.cat([
                _image_tensor(image, device=device, dtype=dtype)
                for image in images[offset:offset + batch_size]
            ])
            latents.append(vae.encode(tensor).latent_dist.mode() * (1.0 / float(vae.config.scaling_factor)))
    return torch.cat(latents)


def _cached_reference_latents(
    *, root: Path, vae: Any, images: list[Any], selected_rows: list[dict[str, str]],
    model_setting: str, watermark: str, key_id: str, batch_size: int,
) -> Any:
    """Reuse exact FP32 reference latents across lambda/N conditions."""
    import torch

    identities = []
    paths = []
    for row in selected_rows:
        identity = stable_hash({
            "model_setting": model_setting, "watermark": watermark, "key_id": key_id,
            "reference_sha256": row["image_sha256"],
            "preprocess": "rgb_bicubic_short_edge_512_center_crop_minus1_plus1",
        })
        identities.append(identity)
        paths.append(root / "reference_latent_cache" / f"{identity}.pt")
    values: list[Any | None] = [None] * len(images)
    missing = []
    for index, path in enumerate(paths):
        if path.is_file():
            try:
                payload = torch.load(path, map_location="cpu")
            except Exception:
                payload = {}
            value = payload.get("latent") if isinstance(payload, dict) else None
            if (
                isinstance(payload, dict) and payload.get("identity") == identities[index]
                and value is not None and value.dtype == torch.float32
                and int(value.shape[0]) == 1
            ):
                values[index] = value
                continue
        missing.append(index)
    for offset in range(0, len(missing), batch_size):
        indices = missing[offset:offset + batch_size]
        encoded = _encode(vae, [images[index] for index in indices], batch_size=len(indices)).detach().float().cpu()
        for local_index, image_index in enumerate(indices):
            value = encoded[local_index:local_index + 1]
            payload = io.BytesIO()
            torch.save({"identity": identities[image_index], "latent": value}, payload)
            atomic_write_bytes(paths[image_index], payload.getvalue())
            values[image_index] = value
    if any(value is None for value in values):
        raise RuntimeError("Reference latent cache construction is incomplete")
    return torch.cat(values).to(device=next(vae.parameters()).device, dtype=next(vae.parameters()).dtype)


def _simple_average(source: Any, references: list[Any], clean: list[Any], task: str = "forgery") -> Any:
    import numpy as np
    import torch
    from PIL import Image
    def tensor(image: Any) -> Any:
        return torch.from_numpy(np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1)
    result = apply_pixel_direction(
        tensor(source),
        estimate_pixel_direction(torch.stack([tensor(x) for x in references]), torch.stack([tensor(x) for x in clean])),
        task, gamma=1.0,
    )
    array = (result.permute(1, 2, 0).numpy() * 255.0).round().clip(0, 255).astype(np.uint8)
    return Image.fromarray(array, mode="RGB")


def _matched_noise(source: Any, attacked: Any, seed: int) -> tuple[Any, float, float, float]:
    import numpy as np
    from PIL import Image
    original = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    attack = np.asarray(attacked.convert("RGB"), dtype=np.float32) / 255.0
    target_l2 = float(np.linalg.norm((attack - original).reshape(-1)))
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(original.shape).astype(np.float32)
    norm = float(np.linalg.norm(noise.reshape(-1)))
    if norm == 0:
        raise RuntimeError("Matched-noise generator produced a zero vector")
    controlled = np.clip(original + noise * (target_l2 / norm), 0.0, 1.0)
    quantized = np.round(controlled * 255.0).clip(0, 255).astype(np.uint8)
    difference = quantized.astype(np.float32) / 255.0 - original
    control_l2 = float(np.linalg.norm(difference.reshape(-1)))
    control_linf = float(np.max(np.abs(difference)))
    return Image.fromarray(quantized, mode="RGB"), target_l2, control_l2, control_linf


def _reference_rows(run_dir: Path) -> dict[tuple[str, str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in read_csv(run_dir / "manifests/reference_manifest.csv"):
        grouped.setdefault((row["model_setting"], row["watermark"], row["key_id"]), []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["selected_reference_index"]))
    return grouped


def _source_rows(root: Path, task: str, target_by_key: dict[str, dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
    if task == "forgery":
        return {
            (model_setting, watermark, key_id): row
            for model_setting in ("same_model_sd14_target_sd14_vae_proxy", "cross_model_sd2_target_sd14_vae_proxy")
            for watermark in ("tree_ring", "ringid", "gaussian_shading")
            for key_id, row in target_by_key.items()
        }
    return {
        (row["model_setting"], row["watermark"], row["key_id"]): {
            "path": str(root / row["target_path"]),
            "image_id": row["target_id"],
            "sha256": sha256_file(root / row["target_path"]),
        }
        for row in read_csv(root / "evaluation/e0_original_detection.csv")
    }


def _cleanup_consumed_reference_images(root: Path, rows: list[dict[str, Any]], expected: int) -> dict[str, Any]:
    """Delete selected reference PNGs only after every primary attack output is verified."""
    report_path = root / "logs/reference_image_cleanup.json"
    if report_path.is_file():
        import json
        return json.loads(report_path.read_text(encoding="utf-8"))
    (root / "logs").mkdir(parents=True, exist_ok=True)
    identities = {row["condition_id"] + "|" + row["key_id"] for row in rows}
    if len(rows) != expected or len(identities) != expected:
        raise RuntimeError("Reference images cannot be cleaned before all primary outputs complete")
    for row in rows:
        output = root / row["output_image_path"]
        if not output.is_file() or sha256_file(output) != row["output_sha256"]:
            raise RuntimeError(f"Reference cleanup blocked by invalid attack output: {output}")
    reference_rows = read_csv(root / "manifests/reference_manifest.csv")
    preparation = __import__("json").loads(
        (root / "preparation_report.json").read_text(encoding="utf-8")
    )
    if len(reference_rows) != int(preparation["selected_reference_count"]):
        raise RuntimeError("Reference cleanup blocked by an incomplete reference manifest")
    inventory = []
    for row in reference_rows:
        path = (root / row["image_path"]).resolve()
        allowed = (root / "prepared_inputs/references").resolve()
        if not path.is_relative_to(allowed):
            raise RuntimeError(f"Unsafe reference cleanup path: {path}")
        if not path.is_file() or sha256_file(path) != row["image_sha256"]:
            raise RuntimeError(f"Reference cleanup blocked by missing or corrupt image: {path}")
        inventory.append({
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": row["image_sha256"],
        })
    atomic_write_json(root / "logs/reference_image_cleanup_inventory.json", inventory)
    for item in inventory:
        (root / item["path"]).unlink()
    reference_root = root / "prepared_inputs/references"
    for directory in sorted(
        (path for path in reference_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts), reverse=True,
    ):
        directory.rmdir()
    reference_root.rmdir()
    report = {
        "status": "COMPLETE",
        "removed_files": len(inventory),
        "removed_bytes": sum(int(item["size_bytes"]) for item in inventory),
        "trigger": "all_primary_attack_outputs_sha256_verified",
        "retained_reference_pngs": 0,
    }
    atomic_write_json(report_path, report)
    append_event(
        root / "logs/unit_ledger.jsonl",
        LedgerEvent("__consumed_reference_image_cleanup__", "COMPLETE", str(report)),
    )
    return report


def _run_iterative_condition_batches(
    *, condition: Any, key_ids: list[str], completed: set[str], root: Path,
    target_by_key: dict[str, dict[str, str]], clean_by_key: dict[str, list[dict[str, str]]],
    references_by_group: dict[tuple[str, str, str], list[dict[str, str]]], vae: Any,
    config: dict[str, Any], config_hash: str, sha: str, run_id: str, ledger_path: Path,
    unit_record_dir: Path, rows: list[dict[str, Any]], total: int, task: str,
    source_by_group: dict[tuple[str, str, str], dict[str, str]],
) -> None:
    """Execute one iterative condition in independent, resume-compatible batches."""
    import torch

    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    budget = int(config[f"T_{task}_formal"])
    batch_size = int(config["validated_batching"]["attack_batch_size"])
    reference_batch_size = int(config["validated_batching"]["reference_encode_batch_size"])
    candidates: list[dict[str, Any]] = []
    for key_id in key_ids:
        preparation_started = time.perf_counter()
        unit_id = condition.id + "|" + key_id
        if unit_id in completed:
            continue
        target_row = source_by_group[(condition.model_setting, condition.watermark, key_id)]
        source = canonical_512(open_rgb(target_row["path"]))
        reference_rows = references_by_group[(condition.model_setting, condition.watermark, key_id)]
        n = int(condition.N or 1)
        selected_rows = reference_rows[:n]
        references = [open_rgb(root / row["image_path"]) for row in selected_rows]
        clean_rows = [] if task == "removal" and condition.method == "jain" else clean_by_key[key_id][:n]
        seed = derive_seed("worker", "formal", unit_id)
        input_hash = stable_hash({
            "condition": condition.id, "key_id": key_id,
            "target_sha256": target_row.get("sha256"),
            "reference_sha256": [row["image_sha256"] for row in selected_rows],
            "clean_sha256": [row.get("sha256") for row in clean_rows],
        })
        source_tensor = _image_tensor(source, device=device, dtype=dtype)
        reference_latents = None
        if task == "forgery" or condition.method == "proposed":
            reference_latents = _cached_reference_latents(
                root=root, vae=vae, images=references, selected_rows=selected_rows,
                model_setting=condition.model_setting, watermark=condition.watermark,
                key_id=key_id, batch_size=reference_batch_size,
            )
        if task == "forgery":
            assert reference_latents is not None
            target_latent = (
                jain_forgery_target(reference_latents)
                if condition.method == "jain" else forgery_target(reference_latents)
            )
        elif condition.method == "jain":
            with torch.inference_mode():
                target_latent = (
                    vae.encode(jain_removal_mean_image(source_tensor)).latent_dist.mode()
                    * (1.0 / float(vae.config.scaling_factor))
                ).detach().float()
        else:
            assert reference_latents is not None
            clean_images = [canonical_512(open_rgb(row["path"])) for row in clean_rows]
            clean_latents = _encode(vae, clean_images, batch_size=reference_batch_size)
            source_latent = _encode(vae, [source], batch_size=1)
            target_latent = removal_target(
                source_latent, reference_latents, clean_latents, float(condition.beta),
            )
        resume_path = root / "resume_state" / f"{stable_hash(unit_id)}.pkl"
        start_step, current, history, prior_time, saved_rng_state = 0, source_tensor, [], 0.0, None
        if resume_path.is_file():
            try:
                state = load_resume_state(
                    resume_path, expected_unit_id=unit_id, input_hash=input_hash,
                    resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=sha,
                )
                start_step, current, history = state.step, state.image_tensor, state.loss_history
                prior_time = float(state.timing.get("optimization_compute_time", 0.0))
                saved_rng_state = state.rng_state
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"resumed_from_step={start_step}"))
            except (FileNotFoundError, ValueError) as exc:
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"corrupt_resume_restart={exc}"))
        candidates.append({
            "unit_id": unit_id, "key_id": key_id, "target_row": target_row,
            "source_tensor": source_tensor, "target_latent": target_latent,
            "selected_rows": selected_rows, "clean_rows": clean_rows,
            "seed": seed, "input_hash": input_hash, "resume_path": resume_path,
            "start_step": start_step, "current": current, "history": history,
            "prior_time": prior_time,
            "saved_rng_state": saved_rng_state,
            "preparation_time": time.perf_counter() - preparation_started,
            "started": 0.0,
        })
    for start_step in sorted({item["start_step"] for item in candidates}):
        group = [item for item in candidates if item["start_step"] == start_step]
        for offset in range(0, len(group), batch_size):
            batch = group[offset:offset + batch_size]
            with ExitStack() as stack:
                if len(batch) != 1:
                    raise RuntimeError("formal_protocol_v1.22 requires scalar attack batches")
                if batch[0]["saved_rng_state"] is None:
                    seed_runtime(batch[0]["seed"], torch)
                else:
                    restore_rng_state(batch[0]["saved_rng_state"], torch)
                for item in batch:
                    item["started"] = time.perf_counter()
                    stack.enter_context(UnitLock(root / "logs/locks" / f"{stable_hash(item['unit_id'])}.lock"))
                    append_event(ledger_path, LedgerEvent(item["unit_id"], "RUNNING", f"batch_size={len(batch)}"))
                callback_started = time.perf_counter()
                checkpoint_callbacks = []
                for item in batch:
                    def checkpoint(step: int, image: Any, history: list[dict[str, Any]], item: dict[str, Any] = item) -> None:
                        elapsed = item["prior_time"] + (time.perf_counter() - callback_started) / len(batch)
                        save_resume_state(item["resume_path"], ResumeState(
                            unit_id=item["unit_id"], step=step, image_tensor=image.detach().cpu(),
                            loss_history=history, rng_state=capture_rng_state(torch),
                            timing={"optimization_compute_time": elapsed}, input_hash=item["input_hash"],
                            resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=sha,
                        ))
                    checkpoint_callbacks.append(checkpoint)
                result = optimize_fixed_budget_batch(
                    torch.cat([item["source_tensor"] for item in batch]),
                    torch.cat([item["target_latent"] for item in batch]), vae,
                    lambda_pixels=[float(condition.lambda_pixel)] * len(batch),
                    learning_rate=float(config["learning_rate"]), final_step=budget,
                    start_step=start_step,
                    current_images=torch.cat([item["current"] for item in batch]),
                    original_images=torch.cat([item["source_tensor"] for item in batch]),
                    histories=[item["history"] for item in batch],
                    checkpoint_callbacks=checkpoint_callbacks,
                )
                amortized_time = result.optimization_compute_time / len(batch)
                for index, item in enumerate(batch):
                    image = result.images[index:index + 1]
                    compute_time = item["prior_time"] + amortized_time
                    save_resume_state(item["resume_path"], ResumeState(
                        unit_id=item["unit_id"], step=result.final_step, image_tensor=image.detach().cpu(),
                        loss_history=result.loss_histories[index], rng_state=capture_rng_state(torch),
                        timing={"optimization_compute_time": compute_time}, input_hash=item["input_hash"],
                        resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=sha,
                    ))
                    final_pil = _tensor_pil(image)
                    relative = Path("evaluation_spool") / condition.id / f"{item['key_id']}.png"
                    output_hash = atomic_png(root / relative, final_pil)
                    row = {
                        "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                        "condition_id": condition.id, "experiment": condition.experiment,
                        "task": task, "watermark": condition.watermark,
                        "model_setting": condition.model_setting, "method": condition.method,
                        "key_id": item["key_id"], "target_id": item["target_row"].get("image_id", item["key_id"]),
                        "reference_ids": ";".join(value["image_sha256"] for value in item["selected_rows"]),
                        "clean_ids": ";".join(value.get("image_id", "") for value in item["clean_rows"]),
                        "N": int(condition.N or 1), "lambda": condition.lambda_pixel,
                        "beta": condition.beta if condition.beta is not None else "", "gamma": "", "seed": item["seed"],
                        "final_step": result.final_step, "optimization_compute_time": compute_time,
                        "input_hash": item["input_hash"],
                        "unit_wall_time": item["preparation_time"] + time.perf_counter() - item["started"],
                        "output_sha256": output_hash, "output_image_path": relative.as_posix(),
                        "control_parent_condition_id": "", "matched_parent_l2_preclip": "",
                        "matched_control_l2_postclip": "", "matched_control_linf_postclip": "",
                    }
                    rows.append(row)
                    atomic_write_json(unit_record_dir / f"{stable_hash(item['unit_id'])}.json", row)
                    append_event(ledger_path, LedgerEvent(item["unit_id"], "COMPLETE", f"batch_size={len(batch)}"))
                    completed.add(item["unit_id"])
                    _write_attack_progress(root, rows, total)
            torch.cuda.empty_cache()


def _run_formal_attack(
    *, config: dict[str, Any], assets_lock: dict[str, Any], run_dir: str | Path,
    run_id: str, key_ids: list[str], project_root: str | Path, task: str,
) -> dict[str, Any]:
    """Detector-free formal attack process. This module deliberately has no detector dependency."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Formal attack requires a CUDA GPU")
    configure_torch_determinism(torch)
    root = ensure_run_layout(run_dir)
    attack_report_path = root / "attack_report.json"
    completed_evaluation = False
    for report_name in ("evaluation_report.json", "smoke_report.json"):
        report_path = root / report_name
        if not report_path.is_file():
            continue
        import json
        evaluation_report = json.loads(report_path.read_text(encoding="utf-8"))
        hashes = evaluation_report.get("hashes", {})
        completed_evaluation = bool(hashes) and all(
            (root / relative).is_file() and sha256_file(root / relative) == digest
            for relative, digest in hashes.items()
        )
        if completed_evaluation:
            break
    if attack_report_path.is_file() and completed_evaluation:
        import json
        return json.loads(attack_report_path.read_text(encoding="utf-8"))
    preparation = root / "preparation_report.json"
    if not preparation.is_file():
        raise RuntimeError("Preparation must complete before the detector-free attack starts")
    assets = assets_by_name(assets_lock)
    _, target_by_key, clean_by_key = formal_inputs(assets)
    references_by_group = _reference_rows(root)
    source_by_group = _source_rows(root, task, target_by_key)
    conditions = conditions_for_task(task)
    expected = len(conditions) * len(key_ids)
    e7_parent_count = sum(condition.experiment != "E6" for condition in conditions) * len(key_ids)
    total_with_e7 = expected + e7_parent_count
    results_path = root / "manifests/attack_outputs.csv"
    unit_record_dir = root / "manifests/attack_units"
    unit_record_dir.mkdir(parents=True, exist_ok=True)
    import json
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(unit_record_dir.glob("*.json"))]
    valid_rows = []
    for row in rows:
        output = root / row["output_image_path"]
        if output.is_file() and sha256_file(output) == row["output_sha256"]:
            valid_rows.append(row)
    rows = valid_rows
    ledger_path = root / "logs/unit_ledger.jsonl"
    sha = git_sha(project_root)
    config_hash = config["resolved_config_hash"]
    verified_complete = []
    for row in rows:
        unit_id = row["condition_id"] + "|" + row["key_id"]
        if row["method"] in {"jain", "proposed"}:
            resume_path = root / "resume_state" / f"{stable_hash(unit_id)}.pkl"
            try:
                state = load_resume_state(
                    resume_path, expected_unit_id=unit_id, input_hash=row["input_hash"],
                    resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION,
                    git_sha=sha,
                )
                if state.step != int(config[f"T_{task}_formal"]):
                    raise ValueError("completed unit resume state is not at the final step")
            except (FileNotFoundError, ValueError) as exc:
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"invalid_complete_restart={exc}"))
                continue
        verified_complete.append(row)
    if len(verified_complete) != len(rows):
        rows = verified_complete
        atomic_csv(results_path, rows, ATTACK_FIELDS)
    completed = {row["condition_id"] + "|" + row["key_id"] for row in rows}
    atomic_write_text(root / "logs/attack_command.txt", " ".join(__import__("sys").argv) + "\n")

    vae = load_proxy_vae(model_config(assets, "same_model_sd14_target_sd14_vae_proxy"), offline=True)
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    budget = int(config[f"T_{task}_formal"])
    for condition in conditions:
        if condition.method in {"jain", "proposed"}:
            _run_iterative_condition_batches(
                condition=condition, key_ids=key_ids, completed=completed, root=root,
                target_by_key=target_by_key, clean_by_key=clean_by_key,
                references_by_group=references_by_group, vae=vae, config=config,
                config_hash=config_hash, sha=sha, run_id=run_id, ledger_path=ledger_path,
                unit_record_dir=unit_record_dir,
                rows=rows, total=total_with_e7, task=task,
                source_by_group=source_by_group,
            )
            atomic_csv(results_path, rows, ATTACK_FIELDS)
            continue
        for key_id in key_ids:
            unit_id = condition.id + "|" + key_id
            if unit_id in completed:
                continue
            with UnitLock(root / "logs/locks" / f"{stable_hash(unit_id)}.lock"):
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING"))
                target_row = source_by_group[(condition.model_setting, condition.watermark, key_id)]
                source = canonical_512(open_rgb(target_row["path"]))
                reference_rows = references_by_group[(condition.model_setting, condition.watermark, key_id)]
                n = 0 if condition.method == "distortion" else int(condition.N or 1)
                selected_rows = reference_rows[:n]
                references = [open_rgb(root / row["image_path"]) for row in selected_rows]
                clean_rows = clean_by_key[key_id][:n]
                clean_images = [canonical_512(open_rgb(row["path"])) for row in clean_rows]
                seed = derive_seed("worker", "formal", unit_id)
                input_hash = stable_hash({
                    "condition": condition.id,
                    "key_id": key_id,
                    "target_sha256": target_row.get("sha256"),
                    "reference_sha256": [row["image_sha256"] for row in selected_rows],
                    "clean_sha256": [row.get("sha256") for row in clean_rows],
                })
                relative = Path("evaluation_spool") / condition.id / f"{key_id}.png"
                started = time.perf_counter()
                final_step = 0
                if condition.method == "simple_averaging":
                    final_pil = _simple_average(source, references, clean_images, task)
                    compute_time = time.perf_counter() - started
                elif condition.method == "distortion":
                    final_pil = apply_distortion(source, str(condition.transform), seed=seed)
                    compute_time = time.perf_counter() - started
                else:
                    source_tensor = _image_tensor(source, device=device, dtype=dtype)
                    reference_latents = _encode(vae, references, batch_size=1)
                    target_latent = (
                        jain_forgery_target(reference_latents)
                        if condition.method == "jain" else forgery_target(reference_latents)
                    )
                    resume_path = root / "resume_state" / f"{stable_hash(unit_id)}.pkl"
                    start_step, current, history, prior_time = 0, source_tensor, None, 0.0
                    if resume_path.is_file():
                        try:
                            state = load_resume_state(
                                resume_path, expected_unit_id=unit_id, input_hash=input_hash,
                                resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION,
                                git_sha=sha,
                            )
                            restore_rng_state(state.rng_state, torch)
                            start_step, current, history = state.step, state.image_tensor, state.loss_history
                            prior_time = float(state.timing.get("optimization_compute_time", 0.0))
                            append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"resumed_from_step={start_step}"))
                        except (FileNotFoundError, ValueError) as exc:
                            append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"corrupt_resume_restart={exc}"))
                            seed_runtime(seed, torch)
                    else:
                        seed_runtime(seed, torch)
                    callback_started = time.perf_counter()
                    def checkpoint(step: int, image: Any, loss_history: list[dict[str, Any]]) -> None:
                        elapsed = prior_time + time.perf_counter() - callback_started
                        save_resume_state(resume_path, ResumeState(
                            unit_id=unit_id, step=step, image_tensor=image.detach().cpu(),
                            loss_history=loss_history, rng_state=capture_rng_state(torch),
                            timing={"optimization_compute_time": elapsed}, input_hash=input_hash,
                            resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION,
                            git_sha=sha,
                        ))
                    result = optimize_fixed_budget(
                        source_tensor, target_latent, vae,
                        lambda_pixel=float(condition.lambda_pixel),
                        learning_rate=float(config["learning_rate"]), final_step=budget,
                        start_step=start_step, current_image=current, original_image=source_tensor,
                        history=history, checkpoint_callback=checkpoint,
                    )
                    final_pil = _tensor_pil(result.image)
                    final_step = result.final_step
                    compute_time = prior_time + result.optimization_compute_time
                    save_resume_state(resume_path, ResumeState(
                        unit_id=unit_id, step=final_step, image_tensor=result.image.detach().cpu(),
                        loss_history=result.loss_history, rng_state=capture_rng_state(torch),
                        timing={"optimization_compute_time": compute_time}, input_hash=input_hash,
                        resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION,
                        git_sha=sha,
                    ))
                output_hash = atomic_png(root / relative, final_pil)
                row = {
                    "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                    "condition_id": condition.id, "experiment": condition.experiment,
                    "task": task, "watermark": condition.watermark,
                    "model_setting": condition.model_setting, "method": condition.method,
                    "key_id": key_id, "target_id": target_row.get("image_id", key_id),
                    "reference_ids": ";".join(row["image_sha256"] for row in selected_rows),
                    "clean_ids": ";".join(row.get("image_id", "") for row in clean_rows),
                    "N": n if condition.N is not None else "", "lambda": condition.lambda_pixel if condition.lambda_pixel is not None else "",
                    "beta": condition.beta if condition.beta is not None else "", "gamma": condition.gamma if condition.gamma is not None else "",
                    "seed": seed, "final_step": final_step,
                    "optimization_compute_time": compute_time, "input_hash": input_hash,
                    "unit_wall_time": time.perf_counter() - started,
                    "output_sha256": output_hash, "output_image_path": relative.as_posix(),
                    "control_parent_condition_id": "", "matched_parent_l2_preclip": "",
                    "matched_control_l2_postclip": "", "matched_control_linf_postclip": "",
                }
                rows.append(row)
                atomic_write_json(unit_record_dir / f"{stable_hash(unit_id)}.json", row)
                append_event(ledger_path, LedgerEvent(unit_id, "COMPLETE"))
                completed.add(unit_id)
                _write_attack_progress(root, rows, total_with_e7)
                del references, clean_images
                torch.cuda.empty_cache()
        atomic_csv(results_path, rows, ATTACK_FIELDS)
    identities = {row["condition_id"] + "|" + row["key_id"] for row in rows}
    if len(rows) != expected or len(identities) != expected:
        raise RuntimeError(f"Formal forgery produced {len(rows)} outputs; expected {expected}")
    for row in rows:
        final_step = int(row["final_step"])
        if row["method"] in {"jain", "proposed"} and final_step != budget:
            raise RuntimeError(f"Iterative unit did not reach the frozen budget: {row['condition_id']}|{row['key_id']}")
        if row["method"] in {"simple_averaging", "distortion"} and final_step != 0:
            raise RuntimeError("Non-iterative methods must be recorded at step zero")
    reference_cleanup = _cleanup_consumed_reference_images(root, rows, expected)
    control_record_dir = root / "manifests/e7_control_units"
    control_record_dir.mkdir(parents=True, exist_ok=True)
    import json
    control_rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(control_record_dir.glob("*.json"))]
    valid_controls = []
    for row in control_rows:
        output = root / row["output_image_path"]
        if output.is_file() and sha256_file(output) == row["output_sha256"]:
            valid_controls.append(row)
    control_rows = valid_controls
    completed_controls = {row["condition_id"] + "|" + row["key_id"] for row in control_rows}
    e7_parents = [row for row in rows if row["experiment"] != "E6"]
    for parent in e7_parents:
        control_condition = "e7_matched_noise_of__" + parent["condition_id"]
        control_unit = control_condition + "|" + parent["key_id"]
        if control_unit in completed_controls:
            continue
        started = time.perf_counter()
        source = canonical_512(open_rgb(source_by_group[(parent["model_setting"], parent["watermark"], parent["key_id"])]["path"]))
        attacked = open_rgb(root / parent["output_image_path"])
        seed = derive_seed("transform", "E7", parent["condition_id"], parent["key_id"])
        controlled, target_l2, control_l2, control_linf = _matched_noise(source, attacked, seed)
        relative = Path("evaluation_spool/e7_matched_noise") / parent["condition_id"] / f"{parent['key_id']}.png"
        output_hash = atomic_png(root / relative, controlled)
        record = {
            **parent, "condition_id": control_condition, "experiment": "E7",
            "method": "matched_gaussian_noise", "seed": seed, "final_step": 0,
            "optimization_compute_time": time.perf_counter() - started,
            "unit_wall_time": time.perf_counter() - started,
            "input_hash": stable_hash({"parent_output_sha256": parent["output_sha256"], "seed": seed}),
            "output_sha256": output_hash, "output_image_path": relative.as_posix(),
            "control_parent_condition_id": parent["condition_id"],
            "matched_parent_l2_preclip": target_l2,
            "matched_control_l2_postclip": control_l2,
            "matched_control_linf_postclip": control_linf,
        }
        control_rows.append(record)
        atomic_write_json(control_record_dir / f"{stable_hash(control_unit)}.json", record)
        append_event(ledger_path, LedgerEvent(control_unit, "COMPLETE", "E7 matched-noise control"))
        completed_controls.add(control_unit)
        _write_attack_progress(root, rows + control_rows, total_with_e7)
    if len(control_rows) != e7_parent_count or len(completed_controls) != e7_parent_count:
        raise RuntimeError(f"E7 produced {len(control_rows)} controls; expected {e7_parent_count}")
    all_rows = rows + control_rows
    atomic_csv(results_path, all_rows, ATTACK_FIELDS)
    report = {
        "status": "ATTACK_COMPLETE", "run_id": run_id, "task": task, "unit_count": expected,
        "e7_control_unit_count": e7_parent_count, "total_output_count": len(all_rows),
        "validated_batching": config["validated_batching"],
        "reference_latent_cache_file_count": len(list((root / "reference_latent_cache").glob("*.pt"))),
        "reference_image_cleanup": reference_cleanup,
    }
    atomic_write_json(attack_report_path, report)
    return report


def run_formal_forgery_attack(**kwargs: Any) -> dict[str, Any]:
    return _run_formal_attack(task="forgery", **kwargs)


def run_formal_removal_attack(**kwargs: Any) -> dict[str, Any]:
    return _run_formal_attack(task="removal", **kwargs)
