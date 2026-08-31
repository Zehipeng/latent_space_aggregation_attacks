from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.evaluation.eligibility import success as attack_success
from latent_space_aggregation_attacks.methods.proposed.optimizer import optimize_fixed_budget
from latent_space_aggregation_attacks.methods.proposed.targets import forgery_target, removal_target
from latent_space_aggregation_attacks.models.loaders import load_proxy_vae, load_target_pipeline
from latent_space_aggregation_attacks.watermarks.base import registered_adapter
from latent_space_aggregation_attacks.watermarks.runtime import image_to_tensor, tensor_to_pil

from .atomic_io import atomic_write_bytes, atomic_write_json, atomic_write_text
from .hashing import sha256_file, stable_hash
from .ledger import LedgerEvent, append_event
from .manifests import write_manifest
from .resume import ResumeState, load_resume_state, save_resume_state
from .seeds import (
    capture_rng_state,
    configure_torch_determinism,
    derive_seed,
    restore_rng_state,
    seed_runtime,
)


P0_WATERMARK_REVISIONS = {
    "tree_ring": "3015283d9cf82e90b628f02ad2121bd37408ca9a",
    "ringid": "45631a59aecd7d63ccdb640aaaf3e616fdb89fb9",
    "gaussian_shading": "09c678fadc7545acf7be12647ddf2a5e66f6a9dc",
}


def _assets_by_name(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in lock["assets"]}


def _require_gpu_runtime() -> None:
    try:
        import torch
        from Crypto.Cipher import ChaCha20  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("P0 GPU dependencies are incomplete; install requirements.lock before running") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("P0 requires a CUDA GPU; no CUDA device is available")
    configure_torch_determinism(torch)


def _git_sha(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, check=True,
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _atomic_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    temporary.replace(path)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty manifest: {path}")
    _atomic_csv(path, rows, list(rows[0]))


def _bind_run_identity(path: Path, payload: dict[str, Any]) -> None:
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        recorded_hash = existing.pop("manifest_hash", None)
        if recorded_hash != stable_hash(existing):
            raise ValueError("Existing run_manifest.json is corrupt")
        if existing != payload:
            raise RuntimeError("Run identity changed; choose a new run-id instead of mixing outputs")
        return
    write_manifest(path, payload)


def _ensure_layout(path: Path) -> Path:
    names = (
        "protocol_snapshot", "manifests", "logs", "checkpoints_visualization_keys",
        "resume_state", "final_images_visualization_keys", "evaluation_spool",
        "curve_checkpoint_spool", "evaluation", "figures",
    )
    for name in names:
        (path / name).mkdir(parents=True, exist_ok=True)
    return path


def _load_inputs(assets: dict[str, dict[str, Any]]) -> tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, str]], dict[str, list[dict[str, str]]]]:
    prompt_rows = _read_csv(Path(assets["formal-protocol-v1.10-prompt-manifest"]["path"]))
    prompt_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in prompt_rows:
        if row["cohort"] == "pilot":
            prompt_by_key[row["key_id"]].append(row)
    for rows in prompt_by_key.values():
        rows.sort(key=lambda row: int(row["reference_index"]))

    coco_root = Path(assets["formal-protocol-v1.10-coco-manifests"]["path"])
    target_by_key = {row["key_id"]: row for row in _read_csv(coco_root / "p0_forgery_target_manifest.csv")}
    clean_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(coco_root / "p0_clean_prior_manifest.csv"):
        clean_by_key[row["key_id"]].append(row)
    for rows in clean_by_key.values():
        rows.sort(key=lambda row: int(row["clean_index"]))
    if len(prompt_by_key) != 100 or len(target_by_key) != 100 or len(clean_by_key) != 100:
        raise ValueError("P0 manifests must contain exactly 100 pilot keys")
    if any(len(rows) < 64 for rows in prompt_by_key.values()) or any(len(rows) != 5 for rows in clean_by_key.values()):
        raise ValueError("P0 requires 64 preregistered reference candidates and exactly five clean priors per pilot key")
    return prompt_by_key, target_by_key, clean_by_key


def _encode(vae: Any, images: list[Any]) -> Any:
    import torch
    device = next(vae.parameters()).device
    dtype = next(vae.parameters()).dtype
    batch = torch.cat([image_to_tensor(image, size=512, device=device, dtype=dtype) for image in images])
    latents = []
    with torch.inference_mode():
        for item in batch.split(1):
            latents.append(vae.encode(item).latent_dist.mode() * (1.0 / float(vae.config.scaling_factor)))
    return torch.cat(latents)


def _open_rgb(path: str) -> Any:
    from PIL import Image
    with Image.open(path) as image:
        return image.convert("RGB").copy()


def _canonical_detection_image(image: Any) -> Any:
    """Return the same RGB uint8 representation that is persisted as PNG."""
    try:
        import torch
        if torch.is_tensor(image):
            return tensor_to_pil(image)
    except ImportError:
        pass
    return image.convert("RGB")


def _png_payload(image: Any) -> tuple[bytes, str]:
    canonical = _canonical_detection_image(image)
    buffer = io.BytesIO()
    canonical.save(buffer, format="PNG")
    payload = buffer.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


REFERENCE_CONTROL_FIELDS = [
    "protocol_version", "run_id", "stage", "watermark", "key_id",
    "candidate_index", "selected_reference_index", "prompt_sha256",
    "generation_seed", "score", "score_name", "accepted", "selected",
    "image_sha256", "image_path",
]


def _select_valid_references(
    *, adapter: Any, key: Any, watermark: str, key_id: str,
    candidate_rows: list[dict[str, str]], reference_count: int, candidate_limit: int,
    run_dir: Path, run_id: str, stage: str, control_path: Path,
    control_rows: list[dict[str, Any]],
) -> tuple[list[Any], list[dict[str, str]], list[dict[str, Any]]]:
    """Select the first accepted images from a preregistered candidate stream.

    Candidate order, prompts, generation seeds, scores, rejected candidates and
    selected artifacts are all recorded.  The sole selection rule is the first
    ``reference_count`` accepted candidates in the preregistered order.
    """
    from PIL import Image

    group_rows = [
        row for row in control_rows
        if row["watermark"] == watermark and row["key_id"] == key_id
    ]
    selected_existing = sorted(
        [row for row in group_rows if str(row["selected"]).lower() == "true"],
        key=lambda row: int(row["selected_reference_index"]),
    )
    if len(selected_existing) == reference_count:
        images: list[Any] = []
        rows_by_prompt = {row["prompt_sha256"]: row for row in candidate_rows[:candidate_limit]}
        selected_inputs: list[dict[str, str]] = []
        for record in selected_existing:
            source = rows_by_prompt.get(record["prompt_sha256"])
            if source is None or str(record["accepted"]).lower() != "true":
                raise RuntimeError(f"Invalid persisted reference selection: {watermark}/{key_id}")
            path = run_dir / record["image_path"]
            if not path.is_file() or sha256_file(path) != record["image_sha256"]:
                raise RuntimeError(f"Persisted reference image failed integrity check: {path}")
            with Image.open(path) as image:
                images.append(image.convert("RGB").copy())
            selected_inputs.append(source)
        return images, selected_inputs, control_rows

    # A partial selection is deterministically rebuilt for this key.  Rows for
    # other keys remain intact and selected reference artifacts are overwritten
    # atomically with identical content.
    control_rows = [
        row for row in control_rows
        if not (row["watermark"] == watermark and row["key_id"] == key_id)
    ]
    selected_images: list[Any] = []
    selected_inputs: list[dict[str, str]] = []
    for candidate in candidate_rows[:candidate_limit]:
        candidate_index = int(candidate["reference_index"])
        generation_seed = derive_seed(
            "budget_pilot", "generation", watermark, key_id, candidate_index,
        )
        image = _canonical_detection_image(adapter.generate(candidate["prompt"], key, generation_seed))
        detection = adapter.detect(image, key)
        payload, image_hash = _png_payload(image)
        accepted = bool(detection.accepted)
        selected = accepted and len(selected_images) < reference_count
        selected_index: int | str = len(selected_images) if selected else ""
        relative_path = ""
        if selected:
            relative = Path("reference_images") / watermark / key_id / f"ref_{int(selected_index):02d}.png"
            atomic_write_bytes(run_dir / relative, payload)
            relative_path = relative.as_posix()
            selected_images.append(image)
            selected_inputs.append(candidate)
        control_rows.append({
            "protocol_version": PROTOCOL_VERSION, "run_id": run_id, "stage": stage,
            "watermark": watermark, "key_id": key_id,
            "candidate_index": candidate_index,
            "selected_reference_index": selected_index,
            "prompt_sha256": candidate["prompt_sha256"],
            "generation_seed": generation_seed,
            "score": detection.score, "score_name": detection.score_name,
            "accepted": accepted, "selected": selected,
            "image_sha256": image_hash, "image_path": relative_path,
        })
        _atomic_csv(control_path, control_rows, REFERENCE_CONTROL_FIELDS)
        if len(selected_images) == reference_count:
            break
    if len(selected_images) != reference_count:
        raise RuntimeError(
            f"Reference validity gate failed for {watermark}/{key_id}: "
            f"{len(selected_images)}/{reference_count} accepted among {candidate_limit} preregistered candidates"
        )
    return selected_images, selected_inputs, control_rows


def _adapter_config(config: dict[str, Any], watermark: str, pipe: Any, assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    code_names = {"tree_ring": "tree-ring-watermark", "ringid": "RingID", "gaussian_shading": "Gaussian-Shading"}
    locked = assets[code_names[watermark]]
    expected = P0_WATERMARK_REVISIONS[watermark]
    if locked.get("revision") != expected:
        raise ValueError(f"{watermark} revision must be {expected}")
    runtime = dict(config["watermark_runtime"][watermark])
    runtime.update(pipe=pipe, code_revision=expected, code_path=locked["path"])
    return runtime


def _threshold(config: dict[str, Any], watermark: str) -> float:
    runtime = config["watermark_runtime"][watermark]
    return float(runtime["bit_accuracy_threshold"] if watermark == "gaussian_shading" else runtime["p_value_threshold"])


def _load_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        converted: dict[str, Any] = dict(row)
        rows.append(converted)
    return rows


def _write_asr(rows: list[dict[str, Any]], output: Path, steps: list[int]) -> None:
    from latent_space_aggregation_attacks.evaluation.statistics import wilson_interval
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["task"]), str(row["watermark"]))].append(row)
    values = []
    for (task, watermark), group in sorted(grouped.items()):
        eligible = [row for row in group if str(row["eligible"]).lower() == "true"]
        eligible_n = len(eligible)
        for step in steps:
            successes = [row for row in eligible if row["first_success_step"] not in {"", None} and int(row["first_success_step"]) <= step]
            previous = [row for row in eligible if row["first_success_step"] not in {"", None} and int(row["first_success_step"]) < step]
            count = len(successes)
            low, high = wilson_interval(count, eligible_n) if eligible_n else (float("nan"), float("nan"))
            values.append({
                "task": task, "watermark": watermark, "model_setting": "cross_model_sd2_target_sd14_vae_proxy",
                "step": step, "eligible_n": eligible_n, "new_success_n": count - len(previous),
                "cumulative_success_n": count, "cumulative_asr": count / eligible_n if eligible_n else "",
                "wilson_ci_low": low if eligible_n else "", "wilson_ci_high": high if eligible_n else "",
            })
    _atomic_csv(output, values, [
        "task", "watermark", "model_setting", "step", "eligible_n", "new_success_n",
        "cumulative_success_n", "cumulative_asr", "wilson_ci_low", "wilson_ci_high",
    ])


def _plot_p0_curves(csv_path: Path, figure_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = _read_csv(csv_path)
    outputs = []
    for task in ("forgery", "removal"):
        figure, axis = plt.subplots(figsize=(7, 4.5))
        for watermark, label in (("tree_ring", "Tree-Ring"), ("ringid", "RingID"), ("gaussian_shading", "Gaussian Shading")):
            selected = [row for row in rows if row["task"] == task and row["watermark"] == watermark]
            axis.plot([int(row["step"]) for row in selected], [float(row["cumulative_asr"]) if row["cumulative_asr"] else float("nan") for row in selected], marker="o", label=label)
        axis.set(xlabel="Optimization step", ylabel="Cumulative ASR", ylim=(0, 1.02), title=f"P0 {task} online early-stop curve")
        axis.grid(alpha=0.25); axis.legend(); figure.tight_layout()
        destination = figure_dir / f"pilot_{task}_asr_curve.png"
        figure.savefig(destination, dpi=180); plt.close(figure); outputs.append(destination)
    return outputs


RESULT_FIELDS = [
    "protocol_version", "run_id", "stage", "unit_id", "task", "watermark", "model_setting",
    "key_id", "eligible", "initial_score", "final_score", "score_name", "accepted_before",
    "accepted_after", "success", "first_success_step", "executed_steps", "optimization_compute_time",
    "input_hash", "output_sha256",
]


def _run_stage(
    *, config: dict[str, Any], assets_lock: dict[str, Any], output_root: Path,
    run_id: str, key_ids: list[str], stage: str, pipe: Any, vae: Any, project_root: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    import torch

    assets = _assets_by_name(assets_lock)
    prompt_by_key, target_by_key, clean_by_key = _load_inputs(assets)
    run_dir = _ensure_layout(
        output_root / ("smoke/P0" if stage == "smoke" else "budget_selection_pilot") /
        (f"{run_id}_smoke" if stage == "smoke" else run_id)
    )
    git_sha = _git_sha(project_root)
    config_hash = config["resolved_config_hash"]
    candidate_limit = int(config["reference_validity"]["candidate_limit"])
    selected_prompts = [row for key_id in key_ids for row in prompt_by_key[key_id][:candidate_limit]]
    selected_targets = [target_by_key[key_id] for key_id in key_ids]
    selected_clean = [row for key_id in key_ids for row in clean_by_key[key_id]]
    sample_manifest_hash = stable_hash({
        "prompts": selected_prompts, "targets": selected_targets, "clean": selected_clean,
    })
    _bind_run_identity(run_dir / "manifests/run_manifest.json", {
        "protocol_version": PROTOCOL_VERSION, "run_id": run_id, "stage": stage,
        "git_sha": git_sha, "resolved_config_hash": config_hash,
        "assets_lock_hash": stable_hash(assets_lock), "sample_manifest_hash": sample_manifest_hash,
        "key_ids": key_ids,
    })
    source_config = Path(config["_source_path"])
    protocol_source = project_root / "docs/protocols/formal_protocol_v1.10.md"
    shutil.copy2(source_config, run_dir / "protocol_snapshot/source_config.yaml")
    shutil.copy2(protocol_source, run_dir / "protocol_snapshot/formal_protocol_v1.10.md")
    atomic_write_json(run_dir / "protocol_snapshot/config_resolved.json", {k: v for k, v in config.items() if not k.startswith("_")})
    atomic_write_text(run_dir / "logs/command.txt", " ".join(__import__("sys").argv) + "\n")

    _write_rows(run_dir / "manifests/reference_candidate_manifest.csv", selected_prompts)
    _write_rows(run_dir / "manifests/sample_manifest.csv", selected_targets)
    _write_rows(run_dir / "manifests/clean_prior_manifest.csv", selected_clean)
    write_manifest(run_dir / "manifests/key_manifest.json", {
        "protocol_version": PROTOCOL_VERSION,
        "keys": [
            {"key_id": key_id, "watermark": watermark, "watermark_seed": derive_seed("budget_pilot", "watermark_key", watermark, key_id)}
            for watermark in config["watermarks"] for key_id in key_ids
        ],
    })
    result_path = run_dir / "pilot_first_success.csv"
    rows = _load_existing_rows(result_path)
    completed = {str(row["unit_id"]) for row in rows}
    ledger_path = run_dir / "logs/unit_ledger.jsonl"
    reference_control_path = run_dir / "manifests/reference_selection_control.csv"
    reference_controls = _load_existing_rows(reference_control_path)
    visualization_keys = set(config["visualization_key_ids"])

    adapters = {
        watermark: registered_adapter(watermark, _adapter_config(config, watermark, pipe, assets))
        for watermark in config["watermarks"]
    }
    for watermark in config["watermarks"]:
        adapter = adapters[watermark]
        threshold = _threshold(config, watermark)
        for key_id in key_ids:
            if all(f"P0|{task}|{watermark}|{key_id}|proposed" in completed for task in config["tasks"]):
                continue
            key_seed = derive_seed("budget_pilot", "watermark_key", watermark, key_id)
            key_record = {"key_id": key_id, "watermark_seed": key_seed}
            key = adapter.create_key(key_record)
            references, reference_rows, reference_controls = _select_valid_references(
                adapter=adapter, key=key, watermark=watermark, key_id=key_id,
                candidate_rows=prompt_by_key[key_id], reference_count=int(config["main_N"]),
                candidate_limit=candidate_limit, run_dir=run_dir, run_id=run_id, stage=stage,
                control_path=reference_control_path, control_rows=reference_controls,
            )
            reference_latents = _encode(vae, references)
            clean_images = [_open_rgb(row["path"]) for row in clean_by_key[key_id]]
            clean_latents = _encode(vae, clean_images)
            cover = _open_rgb(target_by_key[key_id]["path"])
            task_inputs = {"forgery": cover, "removal": references[0]}
            targets = {
                "forgery": forgery_target(reference_latents),
                "removal": removal_target(reference_latents[0:1], reference_latents, clean_latents, float(config["main_beta"])),
            }
            for task in config["tasks"]:
                unit_id = f"P0|{task}|{watermark}|{key_id}|proposed"
                if unit_id in completed:
                    continue
                append_event(ledger_path, LedgerEvent(unit_id, "RUNNING"))
                source_image = task_inputs[task]
                source_tensor = image_to_tensor(
                    source_image, size=512, device=next(vae.parameters()).device,
                    dtype=next(vae.parameters()).dtype,
                )
                initial_detection = adapter.detect(source_image, key)
                eligible, _, _ = attack_success(task, watermark, initial_detection.score, initial_detection.score, threshold)
                input_hash = stable_hash({
                    "task": task, "watermark": watermark, "key_id": key_id,
                    "target": target_by_key[key_id].get("sha256"),
                    "references": [row["prompt_sha256"] for row in reference_rows],
                    "clean": [row.get("sha256") for row in clean_by_key[key_id]],
                    "key_seed": key_seed,
                })
                resume_path = run_dir / "resume_state" / f"{stable_hash(unit_id)[:20]}.pkl"
                start_step = 0
                current_tensor = source_tensor
                history = None
                first_success: int | None = None
                if resume_path.is_file():
                    try:
                        state = load_resume_state(
                            resume_path, expected_unit_id=unit_id, input_hash=input_hash,
                            resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=git_sha,
                        )
                        restore_rng_state(state.rng_state, torch)
                        start_step, current_tensor, history = state.step, state.image_tensor, state.loss_history
                        if state.timing.get("first_success_step") is not None:
                            first_success = int(state.timing["first_success_step"])
                        append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"resumed_from_step={start_step}"))
                    except (FileNotFoundError, ValueError) as exc:
                        append_event(ledger_path, LedgerEvent(unit_id, "RUNNING", f"corrupt_resume_restart={exc}"))
                else:
                    seed_runtime(derive_seed("budget_pilot", task, watermark, "cross_model_sd2_target_sd14_vae_proxy", key_id), torch)

                detections: list[tuple[int, Any]] = []

                def checkpoint(step: int, image: Any, loss_history: list[dict[str, Any]]) -> None:
                    save_resume_state(resume_path, ResumeState(
                        unit_id=unit_id, step=step, image_tensor=image.detach().cpu(), loss_history=loss_history,
                        rng_state=capture_rng_state(torch),
                        timing={"first_success_step": first_success} if first_success is not None else {}, input_hash=input_hash,
                        resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=git_sha,
                    ))

                def stop(step: int, image: Any) -> bool:
                    nonlocal first_success
                    if step % int(config["detection_every"]):
                        return False
                    # Early stopping must use the exact RGB uint8 representation
                    # that would be persisted as the final PNG.
                    detected = adapter.detect(_canonical_detection_image(image), key)
                    detections.append((step, detected))
                    _, succeeded, _ = attack_success(task, watermark, initial_detection.score, detected.score, threshold)
                    if succeeded and first_success is None:
                        first_success = step
                    return bool(succeeded and config["early_stop"])

                result = optimize_fixed_budget(
                    source_tensor, targets[task], vae,
                    lambda_pixel=float(config["main_lambda"]), learning_rate=float(config["learning_rate"]),
                    final_step=int(config["T_max"]), start_step=start_step, current_image=current_tensor,
                    original_image=source_tensor, history=history, checkpoint_callback=checkpoint,
                    stop_callback=stop,
                )
                final_pil = _canonical_detection_image(result.image)
                final_detection = adapter.detect(final_pil, key)
                eligible, succeeded, accepted_after = attack_success(
                    task, watermark, initial_detection.score, final_detection.score, threshold
                )
                png_bytes, output_hash = _png_payload(final_pil)
                if key_id in visualization_keys:
                    image_path = run_dir / "final_images_visualization_keys" / f"{task}_{watermark}_{key_id}.png"
                    atomic_write_bytes(image_path, png_bytes)
                row = {
                    "protocol_version": PROTOCOL_VERSION, "run_id": run_id, "stage": stage,
                    "unit_id": unit_id, "task": task, "watermark": watermark,
                    "model_setting": "cross_model_sd2_target_sd14_vae_proxy", "key_id": key_id,
                    "eligible": bool(eligible), "initial_score": initial_detection.score,
                    "final_score": final_detection.score, "score_name": final_detection.score_name,
                    "accepted_before": initial_detection.accepted, "accepted_after": accepted_after,
                    "success": bool(succeeded), "first_success_step": first_success if first_success is not None else "",
                    "executed_steps": result.final_step,
                    "optimization_compute_time": result.optimization_compute_time,
                    "input_hash": input_hash, "output_sha256": output_hash,
                }
                rows.append(row)
                _atomic_csv(result_path, rows, RESULT_FIELDS)
                append_event(ledger_path, LedgerEvent(unit_id, "COMPLETE"))
            del references, reference_latents, clean_images, clean_latents
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    expected = len(key_ids) * len(config["watermarks"]) * len(config["tasks"])
    if len(rows) != expected or len({row["unit_id"] for row in rows}) != expected:
        raise RuntimeError(f"{stage} produced {len(rows)} unique rows; expected {expected}")
    for row in rows:
        if not math.isfinite(float(row["initial_score"])) or not math.isfinite(float(row["final_score"])):
            raise RuntimeError(f"Non-finite detector score: {row['unit_id']}")
        resume_path = run_dir / "resume_state" / f"{stable_hash(row['unit_id'])[:20]}.pkl"
        load_resume_state(
            resume_path, expected_unit_id=str(row["unit_id"]), input_hash=str(row["input_hash"]),
            resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=git_sha,
        )
        if row["key_id"] in visualization_keys:
            image_path = run_dir / "final_images_visualization_keys" / f"{row['task']}_{row['watermark']}_{row['key_id']}.png"
            if sha256_file(image_path) != row["output_sha256"]:
                raise RuntimeError(f"Smoke output hash mismatch: {image_path}")
    selected_controls = [
        row for row in reference_controls if str(row["selected"]).lower() == "true"
    ]
    expected_references = len(key_ids) * len(config["watermarks"]) * int(config["main_N"])
    if len(selected_controls) != expected_references:
        raise RuntimeError(
            f"Reference validity report contains {len(selected_controls)} selected images; "
            f"expected {expected_references}"
        )
    if any(str(row["accepted"]).lower() != "true" for row in selected_controls):
        raise RuntimeError("Reference validity report contains an invalid selected image")
    _atomic_csv(
        run_dir / "manifests/reference_manifest.csv",
        sorted(
            selected_controls,
            key=lambda row: (
                str(row["watermark"]), str(row["key_id"]),
                int(row["selected_reference_index"]),
            ),
        ),
        REFERENCE_CONTROL_FIELDS,
    )
    steps = list(range(int(config["detection_every"]), int(config["T_max"]) + 1, int(config["detection_every"])))
    _write_asr(rows, run_dir / "pilot_asr_by_step.csv", steps)
    figures = _plot_p0_curves(run_dir / "pilot_asr_by_step.csv", run_dir / "figures")
    hashes = {
        "pilot_first_success.csv": sha256_file(result_path),
        "pilot_asr_by_step.csv": sha256_file(run_dir / "pilot_asr_by_step.csv"),
        "manifests/reference_selection_control.csv": sha256_file(reference_control_path),
        "manifests/reference_manifest.csv": sha256_file(run_dir / "manifests/reference_manifest.csv"),
        **{
            str(row["image_path"]): sha256_file(run_dir / str(row["image_path"]))
            for row in selected_controls
        },
        **{path.relative_to(run_dir).as_posix(): sha256_file(path) for path in figures},
    }
    atomic_write_json(run_dir / ("smoke_report.json" if stage == "smoke" else "p0_run_report.json"), {
        "status": "PASSED" if stage == "smoke" else "COMPLETE", "stage": stage,
        "run_id": run_id, "git_sha": git_sha, "resolved_config_hash": config_hash,
        "key_count": len(key_ids), "unit_count": expected,
        "resume_states_validated": expected,
        "reference_candidates_tested": len(reference_controls),
        "valid_references_selected": len(selected_controls),
        "all_selected_references_valid": True,
        "visualization_images_validated": expected if stage == "smoke" else len([row for row in rows if row["key_id"] in visualization_keys]),
        "hashes": hashes,
    })
    checksum_lines = [f"{digest}  {name}" for name, digest in sorted(hashes.items())]
    atomic_write_text(run_dir / "checksums.sha256", "\n".join(checksum_lines) + "\n")
    if stage == "p0":
        atomic_write_text(run_dir / f"{run_id}_预算选择总结.md", (
            f"# P0预算选择实验总结\n\n- 状态：COMPLETE\n- 协议：{PROTOCOL_VERSION}\n"
            f"- run_id：`{run_id}`\n- Git SHA：`{git_sha}`\n- pilot keys：{len(key_ids)}\n"
            f"- 攻击单元：{expected}\n\n本文件只确认P0在线早停曲线已完整生成；"
            "T_candidate须由用户审阅曲线后提出，P0不得并入正式结果。\n"
        ))
    return run_dir, rows


def run_p0(
    *, config: dict[str, Any], assets_lock: dict[str, Any], output_root: str | Path,
    run_id: str, smoke_only: bool, project_root: str | Path,
) -> dict[str, Any]:
    assets = _assets_by_name(assets_lock)
    required = {
        "stable-diffusion-2-base", "stable-diffusion-v1-4", "tree-ring-watermark", "RingID",
        "Gaussian-Shading", "formal-protocol-v1.10-prompt-manifest", "formal-protocol-v1.10-coco-manifests",
    }
    missing = sorted(required - set(assets))
    if missing:
        raise ValueError(f"P0 assets.lock.json is missing: {missing}")
    expected_models = {
        "stable-diffusion-2-base": "f5bc1bd97485577aa0b946fa8a9004e2ec147402",
        "stable-diffusion-v1-4": "133a221b8aa7292a167afc5127cb63fb5005638b",
    }
    for name, revision in expected_models.items():
        if assets[name].get("revision") != revision:
            raise ValueError(f"{name} revision must be {revision}")
    _require_gpu_runtime()
    model = {
        "target_model_path": assets["stable-diffusion-2-base"]["path"],
        "proxy_vae_path": assets["stable-diffusion-v1-4"]["path"],
        "proxy_vae_subfolder": "vae", "dtype": "float16", "device": "cuda",
    }
    pipe = load_target_pipeline(model, offline=True)
    vae = load_proxy_vae(model, offline=True)
    root = Path(output_root).resolve()
    project = Path(project_root).resolve()
    smoke_dir, _ = _run_stage(
        config=config, assets_lock=assets_lock, output_root=root, run_id=run_id,
        key_ids=["pilot_key_000", "pilot_key_001"], stage="smoke", pipe=pipe, vae=vae,
        project_root=project,
    )
    result: dict[str, Any] = {"status": "SMOKE_PASSED", "smoke_dir": str(smoke_dir)}
    if not smoke_only:
        full_dir, _ = _run_stage(
            config=config, assets_lock=assets_lock, output_root=root, run_id=run_id,
            key_ids=[f"pilot_key_{index:03d}" for index in range(100)], stage="p0", pipe=pipe, vae=vae,
            project_root=project,
        )
        result.update(status="P0_COMPLETE", p0_dir=str(full_dir))
    return result
