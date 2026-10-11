from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..attack import optimize_fixed_budget
from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file, stable_hash
from ..core.resume import ResumeState, load_resume_state, save_resume_state
from ..core.seeds import (capture_rng_state, configure_torch_determinism, derive_seed,
                          restore_rng_state, seed_runtime)
from ..formal.attack import _encode, _image_tensor, _tensor_pil
from ..formal.common import (assets_by_name, atomic_csv, atomic_png, canonical_512,
                             formal_inputs, model_config, open_rgb, read_csv)
from ..models.loaders import load_proxy_vae
from . import PROTOCOL_VERSION, TASK_ORDER, WATERMARK_ORDER
from .targets import forgery_target, removal_target


def attack(config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
           key_ids: list[str], git_sha: str) -> dict[str, Any]:
    import torch
    if not torch.cuda.is_available(): raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch); started = time.perf_counter()
    assets = assets_by_name(lock); _, _, clean = formal_inputs(assets)
    references = {(row["watermark"], row["key_id"]): row
                  for row in read_csv(root / "manifests/reference_manifest.csv")}
    vae = load_proxy_vae(model_config(assets, config["model_setting"]), offline=True)
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    records_dir = root / "manifests/attack_units"; records_dir.mkdir(parents=True, exist_ok=True)
    total = len(key_ids) * len(WATERMARK_ORDER) * len(TASK_ORDER); completed = 0
    config_hash = config["resolved_config_hash"]
    peak = int(torch.cuda.max_memory_reserved())
    for watermark in WATERMARK_ORDER:
        for key_id in key_ids:
            ref = references[(watermark, key_id)]
            ref_path = root / ref["image_path"]
            if sha256_file(ref_path) != ref["image_sha256"]: raise RuntimeError("reference SHA mismatch")
            watermarked = open_rgb(ref_path)
            clean_rows = clean[key_id][:5]
            clean_images = [canonical_512(open_rgb(row["path"])) for row in clean_rows]
            z_w = _encode(vae, [watermarked], batch_size=1).float()
            z_clean = _encode(vae, clean_images, batch_size=1).float()
            for task in TASK_ORDER:
                unit = f"{watermark}|{task}|{key_id}"; record_path = records_dir / f"{stable_hash(unit)}.json"
                if record_path.is_file():
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    output = root / record["output_image_path"]
                    if output.is_file() and sha256_file(output) == record["output_sha256"]:
                        completed += 1; continue
                source = watermarked if task == "removal" else clean_images[0]
                source_tensor = _image_tensor(source, device=device, dtype=dtype)
                target = (removal_target(z_w, z_clean, config["beta"]) if task == "removal"
                          else forgery_target(z_clean[0:1], z_w, z_clean, config["beta"]))
                input_hash = stable_hash({"watermark": watermark, "task": task, "key": key_id,
                    "reference": ref["image_sha256"],
                    "clean": [sha256_file(row["path"]) for row in clean_rows]})
                state_path = root / "resume_state" / f"{stable_hash(unit)}.pkl"
                step, current, history, prior = 0, source_tensor, [], 0.0
                seed = derive_seed("worker", PROTOCOL_VERSION, watermark, task, key_id)
                seed_runtime(seed, torch)
                if state_path.is_file():
                    state = load_resume_state(state_path, expected_unit_id=unit, input_hash=input_hash,
                        resolved_config_hash=config_hash, protocol_version=PROTOCOL_VERSION, git_sha=git_sha)
                    step, current, history = state.step, state.image_tensor, state.loss_history
                    prior = state.timing["optimization_compute_time"]; restore_rng_state(state.rng_state, torch)
                unit_started = time.perf_counter()
                def checkpoint(at: int, image: Any, losses: list[dict[str, Any]]) -> None:
                    save_resume_state(state_path, ResumeState(unit_id=unit, step=at,
                        image_tensor=image.detach().cpu(), loss_history=losses,
                        rng_state=capture_rng_state(torch),
                        timing={"optimization_compute_time": prior + time.perf_counter() - unit_started},
                        input_hash=input_hash, resolved_config_hash=config_hash,
                        protocol_version=PROTOCOL_VERSION, git_sha=git_sha))
                if step < int(config["steps"]):
                    result = optimize_fixed_budget(source_tensor, target, vae,
                        lambda_pixel=float(config["lambda_pixel"]),
                        learning_rate=float(config["learning_rate"]), final_step=int(config["steps"]),
                        start_step=step, current_image=current, original_image=source_tensor,
                        history=history, checkpoint_callback=checkpoint,
                        checkpoint_every=int(config["resume_every"]))
                    current = result.image; elapsed = prior + result.optimization_compute_time
                else: elapsed = prior
                relative = Path("evaluation_spool/attacks") / watermark / task / f"{key_id}.png"
                digest = atomic_png(root / relative, _tensor_pil(current))
                record = {"protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                    "watermark": watermark, "task": task, "key_id": key_id,
                    "model_setting": config["model_setting"], "N_watermarked": 1, "N_clean": 5,
                    "beta": config["beta"], "lambda_pixel": config["lambda_pixel"],
                    "seed": seed, "final_step": config["steps"],
                    "optimization_compute_time": elapsed, "input_hash": input_hash,
                    "output_image_path": relative.as_posix(), "output_sha256": digest,
                    "source_path": ref["image_path"] if task == "removal" else clean_rows[0]["path"]}
                atomic_write_json(record_path, record); completed += 1
                peak = max(peak, int(torch.cuda.max_memory_reserved()))
                per = (time.perf_counter() - started) / completed; remaining = total - completed
                atomic_write_json(root / "progress.json", {"stage": "attack", "completed_units": completed,
                    "total_units": total, "remaining_units": remaining,
                    "estimated_remaining_seconds": per * remaining,
                    "estimated_completion_utc": (datetime.now(timezone.utc) + timedelta(seconds=per*remaining)).isoformat()})
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(records_dir.glob("*.json"))]
    atomic_csv(root / "manifests/attack_outputs.csv", rows)
    report = {"status": "ATTACK_COMPLETE", "output_count": len(rows),
              "elapsed_seconds": time.perf_counter() - started,
              "gpu_peak_reserved_bytes": peak, "gpu_name": torch.cuda.get_device_name(0),
              "torch_version": torch.__version__, "torch_cuda_version": torch.version.cuda}
    atomic_write_json(root / "attack_report.json", report); return report
