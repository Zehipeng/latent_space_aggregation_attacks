from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class OptimizationResult:
    image: Any
    final_step: int
    loss_history: list[dict[str, float | int]]
    optimization_compute_time: float


def optimize_fixed_budget(
    image: Any,
    target_latent: Any,
    vae: Any,
    *,
    lambda_pixel: float,
    learning_rate: float,
    final_step: int,
    start_step: int = 0,
    history: list[dict[str, float | int]] | None = None,
    checkpoint_callback: Callable[[int, Any, list[dict[str, float | int]]], None] | None = None,
    curve_callback: Callable[[int, Any], None] | None = None,
    visualization_callback: Callable[[int, Any], None] | None = None,
) -> OptimizationResult:
    """Detector-free, fixed-budget, mean-reduction pixel gradient descent."""
    import torch
    import torch.nn.functional as functional
    if learning_rate != 0.02:
        raise ValueError("formal learning_rate must be 0.02")
    if final_step <= start_step or lambda_pixel < 0:
        raise ValueError("invalid optimization budget")
    if getattr(vae, "is_detector", False):
        raise TypeError("A detector cannot be passed as the proxy VAE")
    device = next(vae.parameters()).device
    dtype = next(vae.parameters()).dtype
    original = image.to(device=device, dtype=dtype).detach()
    current = original.clone().detach()
    target = target_latent.to(device=device, dtype=dtype).detach()
    records = list(history or [])
    vae.eval().requires_grad_(False)
    started = time.perf_counter()
    for step in range(start_step + 1, final_step + 1):
        current.requires_grad_(True)
        encoded = vae.encode(current).latent_dist.mode() * (1.0 / vae.config.scaling_factor)
        latent_loss = functional.mse_loss(encoded, target, reduction="mean")
        pixel_loss = functional.mse_loss(current, original, reduction="mean")
        total_loss = latent_loss + lambda_pixel * pixel_loss
        gradient = torch.autograd.grad(total_loss, current, only_inputs=True)[0]
        current = (current - learning_rate * gradient).clamp(-1.0, 1.0).detach()
        if step == 1 or step == final_step or step % 50 == 0:
            records.append({"step": step, "latent_loss": float(latent_loss), "pixel_loss": float(pixel_loss), "total_loss": float(total_loss)})
        if step % 50 == 0 and checkpoint_callback:
            checkpoint_callback(step, current, records)
        if step % 100 == 0 and curve_callback:
            curve_callback(step, current)
        if step % 150 == 0 and visualization_callback:
            visualization_callback(step, current)
    if final_step % 100 and curve_callback:
        curve_callback(final_step, current)
    if final_step % 150 and visualization_callback:
        visualization_callback(final_step, current)
    return OptimizationResult(current, final_step, records, time.perf_counter() - started)

