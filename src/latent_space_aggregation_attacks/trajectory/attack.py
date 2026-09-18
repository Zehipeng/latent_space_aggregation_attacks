"""Detector-free checkpoint attacks. No watermark imports or queries."""
import time
from ..attack import optimize_fixed_budget
from ..core.atomic_io import atomic_write_json
from ..core.hashing import stable_hash, sha256_file
from ..core.resume import ResumeState, load_resume_state, save_resume_state
from ..core.seeds import configure_torch_determinism, derive_seed, seed_runtime, capture_rng_state, restore_rng_state
from ..formal.attack import _encode, _image_tensor, _tensor_pil
from ..formal.common import assets_by_name, formal_inputs, model_config, open_rgb, canonical_512, read_csv, atomic_png
from ..latent_targets import forgery_target, removal_target
from ..methods.baselines.jain import jain_forgery_target, jain_removal_mean_image
from ..models.loaders import load_proxy_vae
from .common import MODEL, units, checkpoint, verified

def attack(assets, root, identity, task):
    import torch
    configure_torch_determinism(torch)
    amap = assets_by_name(assets)
    _, covers, clean = formal_inputs(amap)
    prep = root / "shared_preparation"
    grouped = {}
    for row in read_csv(prep / "manifests/reference_manifest.csv"):
        grouped.setdefault((row["watermark"], row["key_id"]), []).append(row)
    vae = load_proxy_vae(model_config(amap, MODEL), offline=True)
    device, dtype = next(vae.parameters()).device, next(vae.parameters()).dtype
    for index, (wm, method, key) in enumerate(units(task), 1):
        refs = sorted(grouped[(wm, key)], key=lambda r: int(r["selected_reference_index"]))
        if len(refs) != 25:
            raise RuntimeError("Expected 25 preregistered accepted references")
        for r in refs:
            if sha256_file(prep / r["image_path"]) != r["image_sha256"]:
                raise RuntimeError("Reference hash mismatch")
        n = 1 if method == "Single-Img" else 5
        images = [open_rgb(prep / r["image_path"]) for r in refs[:n]]
        source = canonical_512(open_rgb(covers[key]["path"])) if task == "forgery" else images[0]
        input_hash = stable_hash({"source": __import__("hashlib").sha256(source.tobytes()).hexdigest(),
            "refs": refs[:n], "clean": [sha256_file(r["path"]) for r in clean[key][:5]],
            "task": task, "method": method, "watermark": wm})
        paths = [checkpoint(root, task, wm, method, key, s) for s in range(0, 151, 10)]
        if all(p.is_file() for p in paths):
            records = [verified(p, root) for p in paths]
            if any(r["input_hash"] != input_hash for r in records):
                raise RuntimeError("Checkpoint input identity changed")
            print(f"TRAJECTORY_SKIP {task} {index}/160 {wm} {method} {key}", flush=True)
            continue
        tensor = _image_tensor(source, device=device, dtype=dtype)
        latents = _encode(vae, images, batch_size=1)
        if task == "forgery":
            target = jain_forgery_target(latents) if method == "Single-Img" else forgery_target(latents)
        elif method == "Single-Img":
            with torch.inference_mode():
                target = vae.encode(jain_removal_mean_image(tensor)).latent_dist.mode() / vae.config.scaling_factor
        else:
            clean_images = [canonical_512(open_rgb(r["path"])) for r in clean[key][:5]]
            target = removal_target(_encode(vae, [source], batch_size=1), latents,
                                    _encode(vae, clean_images, batch_size=1), 1.5)
        seed = derive_seed("worker", "detector_trajectory_v1", task, wm, key)
        seed_runtime(seed, torch)
        unit = f"{task}|{wm}|{method}|{key}"
        state_path = root / "resume_state" / f"{stable_hash(unit)}.pkl"
        step, current, history, prior = 0, tensor, [], 0.0
        if state_path.exists():
            state = load_resume_state(state_path, expected_unit_id=unit, input_hash=input_hash,
                resolved_config_hash=stable_hash(identity), protocol_version="detector_trajectory_v1", git_sha=identity["git_sha"])
            step, current, history, prior = state.step, state.image_tensor, state.loss_history, state.timing["compute"]
            restore_rng_state(state.rng_state, torch)
            if step not in range(0, 151, 10):
                raise RuntimeError("Invalid resume step")
            for s in range(0, step + 1, 10):
                verified(checkpoint(root, task, wm, method, key, s), root)
        started = time.perf_counter()
        def save(at, image, losses):
            path = checkpoint(root, task, wm, method, key, at)
            png = path.with_suffix(".png")
            digest = atomic_png(png, _tensor_pil(image))
            atomic_write_json(path, {"task": task, "watermark": wm, "method": method, "key_id": key,
                "step": at, "N": n, "lambda": 10000, "beta": 1.5 if task == "removal" and method == "FR-LA" else None,
                "seed": seed, "model_setting": MODEL, "input_hash": input_hash,
                "image_path": png.relative_to(root).as_posix(), "checkpoint_sha256": digest})
            save_resume_state(state_path, ResumeState(unit_id=unit, step=at, image_tensor=image.detach().cpu(),
                loss_history=losses, rng_state=capture_rng_state(torch), timing={"compute": prior + time.perf_counter()-started},
                input_hash=input_hash, resolved_config_hash=stable_hash(identity), protocol_version="detector_trajectory_v1", git_sha=identity["git_sha"]))
            print(f"TRAJECTORY_CHECKPOINT {task} {index}/160 {wm} {method} {key} step={at}/150", flush=True)
        if step == 0:
            save(0, tensor, [])
        if step < 150:
            optimize_fixed_budget(tensor, target, vae, lambda_pixel=10000, learning_rate=.02,
                final_step=150, start_step=step, current_image=current, history=history,
                checkpoint_callback=save, checkpoint_every=10)
        atomic_write_json(root / f"{task}_progress.json", {"completed_units": index, "total_units": 160})
