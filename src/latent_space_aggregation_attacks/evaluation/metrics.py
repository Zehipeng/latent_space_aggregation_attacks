from __future__ import annotations

from typing import Any

import numpy as np


def perturbation_metrics(original: np.ndarray, attacked: np.ndarray) -> dict[str, float]:
    if original.shape != attacked.shape:
        raise ValueError("Image arrays must have equal shape")
    diff = attacked.astype(np.float32) - original.astype(np.float32)
    return {
        "l2": float(np.linalg.norm(diff.reshape(-1))),
        "linf": float(np.abs(diff).max()),
        "rmse": float(np.sqrt(np.mean(diff**2))),
    }


def wrong_identity_metrics(target_id: str, scores: dict[str, float], threshold: float, lower_is_accept: bool) -> dict[str, Any]:
    if target_id not in scores:
        raise ValueError("Target identity is absent")
    ordered = sorted(scores, key=scores.get, reverse=not lower_is_accept)
    wrong = [key for key in scores if key != target_id]
    wrong_accepts = sum((scores[key] <= threshold) if lower_is_accept else (scores[key] >= threshold) for key in wrong)
    return {
        "wrong_key_checked": len(wrong),
        "wrong_key_accept_count": wrong_accepts,
        "any_wrong_key_accept": bool(wrong_accepts),
        "target_rank": ordered.index(target_id) + 1,
        "target_top1": ordered[0] == target_id,
    }


def validate_final_row(row: dict[str, Any], t_formal: int) -> None:
    required = {
        "protocol_version", "run_id", "condition_id", "watermark", "model_setting",
        "task", "method", "key_id", "target_id", "reference_ids", "clean_ids",
        "N", "lambda", "beta", "gamma", "seed", "final_step", "l2", "linf",
        "rmse", "lpips", "ssim", "psnr", "attack_compute_time",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"Final row missing fields: {missing}")
    if int(row["final_step"]) != t_formal:
        raise ValueError("Final metric is not from T_formal")

