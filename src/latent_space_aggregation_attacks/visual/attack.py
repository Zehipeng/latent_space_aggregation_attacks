from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..attack import optimize_fixed_budget
from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file, stable_hash
from ..core.resume import ResumeState, load_resume_state, save_resume_state
from ..core.seeds import capture_rng_state, configure_torch_determinism, derive_seed, restore_rng_state, seed_runtime
from ..formal.attack import _encode, _image_tensor, _tensor_pil
from ..formal.common import assets_by_name, atomic_png, canonical_512, formal_inputs, model_config, open_rgb, read_csv
from ..latent_targets import forgery_target, removal_target
from ..models.loaders import load_proxy_vae
from .common import plan, semantic_difference, verified_record


def attack(assets: dict[str, Any], root: Path, identity: dict[str, Any], settings: dict[str, Any]) -> None:
    import torch

    if not torch.cuda.is_available(): raise RuntimeError("Visual attacks require CUDA; switch AutoDL to GPU mode")
    configure_torch_determinism(torch)
    prep = root / "shared_preparation"
    by_key = {key: [] for key in settings["key_ids"]}
    for row in read_csv(prep / "manifests/reference_manifest.csv"):
        by_key[row["key_id"]].append(row)
    for rows in by_key.values():
        rows.sort(key=lambda row: int(row["selected_reference_index"]))
        if len(rows) != 25: raise RuntimeError("Expected exactly 25 references per key")
        for row in rows:
            if sha256_file(prep / row["image_path"]) != row["image_sha256"]:
                raise RuntimeError("Reference SHA mismatch")
    assets_map = assets_by_name(assets)
    _, covers, clean = formal_inputs(assets_map)
    vae = load_proxy_vae(model_config(assets_map, settings["model_setting"]), offline=True)
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    conditions, _ = plan(settings)
    total = len(conditions) * len(settings["key_ids"])
    completed = 0
    config_hash = stable_hash(identity)
    for key in settings["key_ids"]:
        refs = [open_rgb(prep / row["image_path"]) for row in by_key[key]]
        clean_images = [canonical_512(open_rgb(row["path"])) for row in clean[key]]
        reference_latents = _encode(vae, refs, batch_size=1)
        clean_latents = _encode(vae, clean_images, batch_size=1)
        sources = {"forgery": canonical_512(open_rgb(covers[key]["path"])), "removal": refs[0]}
        source_latent = _encode(vae, [sources["removal"]], batch_size=1)
        for condition in conditions:
            cid, task, n = condition["condition_id"], condition["task"], condition["N"]
            unit = f"{cid}|{key}"
            record_path = root / "units" / cid / f"{key}.json"
            source = sources[task]
            input_hash = stable_hash({"condition": condition, "key": key,
                "original_pixels": __import__("hashlib").sha256(source.tobytes()).hexdigest(),
                "references": [r["image_sha256"] for r in by_key[key][:n]],
                "clean": [sha256_file(r["path"]) for r in clean[key][:n]] if task == "removal" else []})
            existing = verified_record(record_path, root)
            if existing:
                if existing["input_hash"] != input_hash: raise RuntimeError("Existing unit input identity changed")
                completed += 1
                print(f"VISUAL_SKIP_VERIFIED {completed}/{total} {unit}", flush=True)
                continue
            target = (forgery_target(reference_latents[:n]) if task == "forgery" else
                removal_target(source_latent, reference_latents[:n], clean_latents[:n], condition["beta"]))
            tensor = _image_tensor(source, device=device, dtype=dtype)
            seed = derive_seed("worker", "visual_ablation_v1", task, key)
            seed_runtime(seed, torch)
            state_path = root / "resume_state" / f"{stable_hash(unit)}.pkl"
            step, current, history, prior_time = 0, tensor, [], 0.0
            if state_path.is_file():
                state = load_resume_state(state_path, expected_unit_id=unit, input_hash=input_hash,
                    resolved_config_hash=config_hash, protocol_version="visual_ablation_v1", git_sha=identity["git_sha"])
                step, current, history = state.step, state.image_tensor, state.loss_history
                prior_time = state.timing["optimization_compute_time"]
                restore_rng_state(state.rng_state, torch)
                if not 0 <= step <= 150: raise RuntimeError("Invalid visual resume step")
            print(f"VISUAL_ATTACK_START {completed+1}/{total} {unit} resume_step={step}", flush=True)
            started = time.perf_counter()
            def checkpoint(at: int, image: Any, losses: list[dict[str, Any]]) -> None:
                save_resume_state(state_path, ResumeState(unit_id=unit, step=at,
                    image_tensor=image.detach().cpu(), loss_history=losses, rng_state=capture_rng_state(torch),
                    timing={"optimization_compute_time": prior_time + time.perf_counter() - started},
                    input_hash=input_hash, resolved_config_hash=config_hash,
                    protocol_version="visual_ablation_v1", git_sha=identity["git_sha"]))
                print(f"VISUAL_CHECKPOINT {unit} step={at}/150", flush=True)
            if step < 150:
                result = optimize_fixed_budget(tensor, target, vae, lambda_pixel=condition["lambda"],
                    learning_rate=0.02, final_step=150, start_step=step, current_image=current,
                    original_image=tensor, history=history, checkpoint_callback=checkpoint)
                current = result.image
                elapsed = prior_time + result.optimization_compute_time
            else:
                elapsed = prior_time
            final = _tensor_pil(current)
            row = {**condition, "key_id": key, "method": "FR-LA", "watermark": "ringid",
                "model_setting": settings["model_setting"], "final_step": 150, "seed": seed,
                "input_hash": input_hash, "optimization_compute_seconds": elapsed}
            for name, image in (("original", source), ("final", final),
                                ("difference", semantic_difference(final, source))):
                relative = Path("images") / task / cid / key / f"{name}.png"
                row[f"{name}_sha256"] = atomic_png(root / relative, image)
                row[f"{name}_path"] = relative.as_posix()
            atomic_write_json(record_path, row)
            completed += 1
            atomic_write_json(root / "progress.json", {"stage": "attack", "completed_units": completed,
                "total_units": total, "last_unit": unit})
            print(f"VISUAL_ATTACK_COMPLETE {completed}/{total} {unit} seconds={elapsed:.2f}", flush=True)
    print("VISUAL_ALL_24_ATTACKS_COMPLETE", flush=True)
