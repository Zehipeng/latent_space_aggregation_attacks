from __future__ import annotations

from typing import Any

import numpy as np


def paired_quality_metrics(original: Any, attacked: Any, lpips_model: Any) -> dict[str, float]:
    """Compute final RGB float32 quality metrics relative to the attacked input."""
    import torch
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity

    original_array = np.asarray(original.convert("RGB"), dtype=np.float32) / 255.0
    attacked_array = np.asarray(attacked.convert("RGB"), dtype=np.float32) / 255.0
    base = perturbation_metrics(original_array, attacked_array)
    original_tensor = torch.from_numpy(original_array).permute(2, 0, 1).unsqueeze(0)
    attacked_tensor = torch.from_numpy(attacked_array).permute(2, 0, 1).unsqueeze(0)
    device = next(lpips_model.parameters()).device
    with torch.inference_mode():
        lpips_value = lpips_model(
            original_tensor.to(device=device) * 2.0 - 1.0,
            attacked_tensor.to(device=device) * 2.0 - 1.0,
        )
    return {
        "l2": base["l2"],
        "linf": base["linf"],
        "LPIPS": float(lpips_value.squeeze().item()),
        "SSIM": float(structural_similarity(original_array, attacked_array, data_range=1.0, channel_axis=2)),
        "PSNR": float(peak_signal_noise_ratio(original_array, attacked_array, data_range=1.0)),
    }


def removal_optimization_progress_pct(
    watermark: str, initial_score: float, final_score: float, threshold: float,
) -> float:
    """Return threshold-normalized removal progress; 100% reaches rejection."""
    if watermark == "gaussian_shading":
        denominator = initial_score - threshold
        numerator = initial_score - final_score
    else:
        denominator = threshold - initial_score
        numerator = final_score - initial_score
    if denominator == 0:
        return 100.0
    if denominator < 0:
        raise ValueError("Removal progress requires an initially accepted eligible sample")
    return float(100.0 * numerator / denominator)


def perturbation_metrics(original: np.ndarray, attacked: np.ndarray) -> dict[str, float]:
    if original.shape != attacked.shape:
        raise ValueError("Image arrays must have equal shape")
    diff = attacked.astype(np.float32) - original.astype(np.float32)
    return {
        "l2": float(np.linalg.norm(diff.reshape(-1))),
        "linf": float(np.abs(diff).max()),
        "rmse": float(np.sqrt(np.mean(diff**2))),
    }


def validate_final_row(row: dict[str, Any], task_budgets: dict[str, int]) -> None:
    required = {
        "protocol_version", "run_id", "condition_id", "watermark", "model_setting",
        "task", "method", "key_id", "target_id", "reference_ids", "clean_ids",
        "N", "lambda", "beta", "gamma", "seed", "final_step", "l2", "linf",
        "rmse", "lpips", "ssim", "psnr", "attack_compute_time",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"Final row missing fields: {missing}")
    task = str(row["task"])
    if task not in task_budgets or int(row["final_step"]) != int(task_budgets[task]):
        raise ValueError("Final metric is not from the frozen task-level budget")
