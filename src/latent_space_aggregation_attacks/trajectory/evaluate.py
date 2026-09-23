"""Separate detector-enabled process, after all task attacks finish."""
import json
import math
from ..core.atomic_io import atomic_write_json
from ..core.hashing import sha256_file
from ..core.seeds import derive_seed, configure_torch_determinism
from ..formal.common import assets_by_name, model_config, adapter_config, open_rgb, atomic_csv
from ..models.loaders import load_target_pipeline
from ..watermarks.base import registered_adapter
from .common import MODEL, units, checkpoint, verified, summarize, checkpoint_steps

def evaluate(config, assets, root, identity, task):
    import torch
    configure_torch_determinism(torch)
    # Verify complete task before enabling any detector evaluation.
    settings = identity["settings"]
    pending = [(wm, method, key, step, verified(checkpoint(root, task, wm, method, key, step), root))
               for wm, method, key in units(task, settings) for step in checkpoint_steps(settings)]
    amap = assets_by_name(assets)
    pipe = load_target_pipeline(model_config(amap, MODEL), offline=True)
    rows = []
    for wm in settings["watermarks"]:
        adapter = registered_adapter(wm, adapter_config(config, wm, pipe, amap))
        for method in settings["methods"]:
            for i in range(int(settings["key_count"])):
                key_id = f"key_{i:03d}"
                key = adapter.create_key({"watermark_seed": derive_seed("watermark_key", wm, key_id)})
                eligible = None
                for _, _, _, step, record in [p for p in pending if p[:3] == (wm, method, key_id)]:
                    cache = root / "detections" / task / wm / method / key_id / f"step_{step:03d}.json"
                    if cache.exists():
                        result = json.loads(cache.read_text(encoding="utf-8"))
                        if result["checkpoint_sha256"] != record["checkpoint_sha256"]:
                            raise RuntimeError("Detection cache hash mismatch")
                    else:
                        detection = adapter.detect(open_rgb(root / record["image_path"]), key)
                        if not math.isfinite(detection.score):
                            raise RuntimeError("Non-finite detector score")
                        result = {**record, "score": float(detection.score), "score_name": detection.score_name,
                            "accepted": bool(detection.accepted), "threshold": adapter.threshold}
                        atomic_write_json(cache, result)
                    if step == 0:
                        eligible = result["accepted"] if task == "removal" else not result["accepted"]
                    rows.append({**result, "eligible": eligible,
                        "p_value": result["score"] if wm == "ringid" else "",
                        "bit_accuracy": result["score"] if wm == "gaussian_shading" else ""})
                    print(f"TRAJECTORY_EVALUATE {task} {wm} {method} {key_id} step={step}", flush=True)
    destination = root / "evaluation" / task
    atomic_csv(destination / "per_key_trajectory.csv", rows)
    atomic_csv(destination / "trajectory_summary.csv", summarize(rows, settings))
    atomic_write_json(destination / "report.json", {"status": "COMPLETE", "task": task, "rows": len(rows),
        "formal_statistics": False, "per_key_sha256": sha256_file(destination / "per_key_trajectory.csv"),
        "summary_sha256": sha256_file(destination / "trajectory_summary.csv")})
