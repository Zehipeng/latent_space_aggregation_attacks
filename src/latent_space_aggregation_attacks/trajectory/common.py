from pathlib import Path
import json
import math
import yaml
from ..core.hashing import sha256_file

MODEL = "cross_model_sd2_target_sd14_vae_proxy"
EXPECTED = {"experiment_version": "detector_trajectory_v1", "key_count": 40,
    "iterations": 150, "record_every": 10, "model_setting": MODEL,
    "watermarks": ["ringid", "gaussian_shading"], "methods": ["Single-Img", "FR-LA"],
    "learning_rate": 0.02, "lambda": 10000.0, "N": 5, "beta": 1.5,
    "aggregation": "arithmetic_mean", "sample_policy": "all_40_keys", "intervals": False}

def load_settings(path):
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if value != EXPECTED:
        raise ValueError("Settings differ from approved detector_trajectory_v1 contract")
    return value

def units(task):
    if task not in ("forgery", "removal"):
        raise ValueError(task)
    return [(wm, method, f"key_{i:03d}") for wm in EXPECTED["watermarks"]
            for method in EXPECTED["methods"] for i in range(40)]

def checkpoint(root, task, wm, method, key, step):
    return root / "checkpoints" / task / wm / method / key / f"step_{step:03d}.json"

def verified(path, root):
    row = json.loads(path.read_text(encoding="utf-8"))
    if sha256_file(root / row["image_path"]) != row["checkpoint_sha256"]:
        raise RuntimeError(f"Checkpoint hash mismatch: {path}")
    return row

def summarize(rows):
    tasks = {r["task"] for r in rows}
    if len(tasks) != 1 or not tasks <= {"forgery", "removal"}:
        raise ValueError("Summary requires exactly one attack task")
    expected_keys = {f"key_{i:03d}" for i in range(40)}
    expected_ids = {(wm, method, key, step) for wm, method, key in units(next(iter(tasks)))
                    for step in range(0, 151, 10)}
    actual_ids = [(r["watermark"], r["method"], r["key_id"], r["step"]) for r in rows]
    if len(actual_ids) != len(expected_ids) or set(actual_ids) != expected_ids:
        raise ValueError("Summary requires all 2560 unique preregistered records")
    output = []
    for wm in EXPECTED["watermarks"]:
        for method in EXPECTED["methods"]:
            group = [r for r in rows if r["watermark"] == wm and r["method"] == method]
            for step in range(0, 151, 10):
                selected = [r for r in group if r["step"] == step]
                if {r["key_id"] for r in selected} != expected_keys:
                    raise ValueError("Missing preregistered key")
                values = [float(r["score"]) for r in selected]
                if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                    raise ValueError("Invalid detector score; do not drop failed keys")
                center = math.fsum(values) / 40
                output.append({"task": rows[0]["task"], "watermark": wm, "method": method,
                    "step": step, "score_name": "p_value" if wm == "ringid" else "bit_accuracy",
                    "center": center, "sample_n": 40,
                    "total_n": 40, "aggregation": "arithmetic_mean", "sample_policy": "all_40_keys",
                    "threshold": .05 if wm == "ringid" else .6484375})
    return output
