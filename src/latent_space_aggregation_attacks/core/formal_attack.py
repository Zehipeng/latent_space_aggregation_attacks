from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.methods.baselines.jain import jain_forgery_target
from latent_space_aggregation_attacks.methods.baselines.simple_averaging import (
    apply_pixel_direction, estimate_pixel_direction,
)
from latent_space_aggregation_attacks.methods.proposed.optimizer import optimize_fixed_budget
from latent_space_aggregation_attacks.methods.proposed.targets import forgery_target
from latent_space_aggregation_attacks.models.loaders import load_proxy_vae

from .atomic_io import atomic_write_json, atomic_write_text
from .conditions import conditions_for_task
from .formal_common import (
    assets_by_name, atomic_csv, atomic_png, canonical_512, ensure_run_layout, formal_inputs,
    git_sha, model_config, open_rgb, read_csv,
)
from .hashing import sha256_file, stable_hash
from .ledger import LedgerEvent, append_event
from .locking import UnitLock
from .resume import ResumeState, load_resume_state, save_resume_state
from .seeds import (
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


def _encode(vae: Any, images: list[Any]) -> Any:
    import torch
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    latents = []
    with torch.inference_mode():
        for image in images:
            tensor = _image_tensor(image, device=device, dtype=dtype)
            latents.append(vae.encode(tensor).latent_dist.mode() * (1.0 / float(vae.config.scaling_factor)))
    return torch.cat(latents)


def _simple_average(source: Any, references: list[Any], clean: list[Any]) -> Any:
    import numpy as np
    import torch
    from PIL import Image
    def tensor(image: Any) -> Any:
        return torch.from_numpy(np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1)
    result = apply_pixel_direction(
        tensor(source),
        estimate_pixel_direction(torch.stack([tensor(x) for x in references]), torch.stack([tensor(x) for x in clean])),
        "forgery", gamma=1.0,
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


def run_formal_forgery_attack(
    *, config: dict[str, Any], assets_lock: dict[str, Any], run_dir: str | Path,
    run_id: str, key_ids: list[str], project_root: str | Path,
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
    conditions = conditions_for_task("forgery")
    expected = len(conditions) * len(key_ids)
    total_with_e7 = expected * 2
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
                if state.step != int(config["T_forgery_formal"]):
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
    budget = int(config["T_forgery_formal"])
    visualization_keys = set(config["visualization_key_ids"])
    for condition in conditions:
        for key_id in key_ids:
            unit_id = condition.id + "|" + key_id
            if unit_id in completed:
                continue
            with UnitLock(root / "logs/locks" / f"{stable_hash(unit_id)}.lock"):
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING"))
                target_row = target_by_key[key_id]
                source = canonical_512(open_rgb(target_row["path"]))
                reference_rows = references_by_group[(condition.model_setting, condition.watermark, key_id)]
                n = int(condition.N or 1)
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
                    final_pil = _simple_average(source, references, clean_images)
                    compute_time = time.perf_counter() - started
                else:
                    source_tensor = _image_tensor(source, device=device, dtype=dtype)
                    reference_latents = _encode(vae, references)
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
                    trajectory = condition.method == "proposed"
                    def curve(step: int, image: Any) -> None:
                        if trajectory:
                            atomic_png(
                                root / "curve_checkpoint_spool" / condition.id / key_id / f"step_{step:04d}.png",
                                _tensor_pil(image),
                            )
                    def visualize(step: int, image: Any) -> None:
                        if key_id in visualization_keys:
                            atomic_png(
                                root / "checkpoints_visualization_keys" / condition.id / key_id / f"step_{step:04d}.png",
                                _tensor_pil(image),
                            )
                    if trajectory and start_step == 0:
                        curve(0, source_tensor)
                    result = optimize_fixed_budget(
                        source_tensor, target_latent, vae,
                        lambda_pixel=float(condition.lambda_pixel),
                        learning_rate=float(config["learning_rate"]), final_step=budget,
                        start_step=start_step, current_image=current, original_image=source_tensor,
                        history=history, checkpoint_callback=checkpoint,
                        curve_callback=curve if trajectory else None,
                        visualization_callback=visualize if key_id in visualization_keys else None,
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
                if key_id in visualization_keys:
                    atomic_png(root / "final_images_visualization_keys" / condition.id / f"{key_id}.png", final_pil)
                row = {
                    "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                    "condition_id": condition.id, "experiment": condition.experiment,
                    "task": "forgery", "watermark": condition.watermark,
                    "model_setting": condition.model_setting, "method": condition.method,
                    "key_id": key_id, "target_id": target_row.get("image_id", key_id),
                    "reference_ids": ";".join(row["image_sha256"] for row in selected_rows),
                    "clean_ids": ";".join(row.get("image_id", "") for row in clean_rows),
                    "N": n, "lambda": condition.lambda_pixel if condition.lambda_pixel is not None else "",
                    "beta": "", "gamma": condition.gamma if condition.gamma is not None else "",
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
    trajectory_files = 0
    for row in rows:
        final_step = int(row["final_step"])
        if row["method"] in {"jain", "proposed"} and final_step != budget:
            raise RuntimeError(f"Iterative unit did not reach the frozen budget: {row['condition_id']}|{row['key_id']}")
        if row["method"] == "simple_averaging" and final_step != 0:
            raise RuntimeError("Simple Averaging must be recorded as a non-iterative method")
        if row["method"] == "proposed":
            checkpoints = list((root / "curve_checkpoint_spool" / row["condition_id"] / row["key_id"]).glob("step_*.png"))
            expected_checkpoints = budget // int(config["trajectory_every"]) + 1
            if len(checkpoints) != expected_checkpoints:
                raise RuntimeError(
                    f"Trajectory spool is incomplete for {row['condition_id']}|{row['key_id']}: "
                    f"{len(checkpoints)}/{expected_checkpoints}"
                )
            trajectory_files += len(checkpoints)
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
    for parent in rows:
        control_condition = "e7_matched_noise_of__" + parent["condition_id"]
        control_unit = control_condition + "|" + parent["key_id"]
        if control_unit in completed_controls:
            continue
        started = time.perf_counter()
        source = canonical_512(open_rgb(target_by_key[parent["key_id"]]["path"]))
        attacked = open_rgb(root / parent["output_image_path"])
        seed = derive_seed("transform", "E7", parent["condition_id"], parent["key_id"])
        controlled, target_l2, control_l2, control_linf = _matched_noise(source, attacked, seed)
        relative = Path("evaluation_spool/e7_matched_noise") / parent["condition_id"] / f"{parent['key_id']}.png"
        output_hash = atomic_png(root / relative, controlled)
        if parent["key_id"] in visualization_keys:
            atomic_png(
                root / "final_images_visualization_keys" / control_condition / f"{parent['key_id']}.png",
                controlled,
            )
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
    if len(control_rows) != expected or len(completed_controls) != expected:
        raise RuntimeError(f"E7 produced {len(control_rows)} controls; expected {expected}")
    all_rows = rows + control_rows
    atomic_csv(results_path, all_rows, ATTACK_FIELDS)
    report = {
        "status": "ATTACK_COMPLETE", "run_id": run_id, "unit_count": expected,
        "e7_control_unit_count": expected, "total_output_count": len(all_rows),
        "trajectory_checkpoint_count": trajectory_files,
    }
    atomic_write_json(attack_report_path, report)
    return report
