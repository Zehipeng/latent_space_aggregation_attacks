from pathlib import Path
import json
import numpy as np
import yaml
from ..core.hashing import sha256_file

MODEL = "cross_model_sd2_target_sd14_vae_proxy"
EXPECTED = {"experiment_version": "detector_trajectory_v1", "key_count": 40,
    "iterations": 150, "record_every": 10, "model_setting": MODEL,
    "watermarks": ["ringid", "gaussian_shading"], "methods": ["Single-Img", "FR-LA"],
    "learning_rate": 0.02, "lambda": 10000.0, "N": 5, "beta": 1.5}

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
    output = []
    for wm in EXPECTED["watermarks"]:
        for method in EXPECTED["methods"]:
            group = [r for r in rows if r["watermark"] == wm and r["method"] == method]
            eligible = {r["key_id"] for r in group if r["step"] == 0 and r["eligible"]}
            for step in range(0, 151, 10):
                values = np.asarray([r["score"] for r in group if r["step"] == step
                                     and r["key_id"] in eligible], dtype=float)
                center = low = high = ""
                if len(values):
                    if wm == "ringid":
                        low, center, high = np.quantile(values, [.25, .5, .75]).tolist()
                    else:
                        center = float(values.mean())
                        rng = np.random.default_rng(205 + step)
                        boot = rng.choice(values, (2000, len(values)), replace=True).mean(axis=1)
                        low, high = np.quantile(boot, [.025, .975]).tolist()
                output.append({"task": rows[0]["task"], "watermark": wm, "method": method,
                    "step": step, "score_name": "p_value" if wm == "ringid" else "bit_accuracy",
                    "center": center, "lower": low, "upper": high, "eligible_n": len(values),
                    "total_n": 40, "aggregation": "median_IQR" if wm == "ringid" else "mean_bootstrap95",
                    "threshold": .05 if wm == "ringid" else .6484375})
    return output
