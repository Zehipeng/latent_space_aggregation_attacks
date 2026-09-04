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
    stopped_early: bool = False


@dataclass
class BatchOptimizationResult:
    images: Any
    final_step: int
    loss_histories: list[list[dict[str, float | int]]]
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
    current_image: Any | None = None,
    original_image: Any | None = None,
    history: list[dict[str, float | int]] | None = None,
    checkpoint_callback: Callable[[int, Any, list[dict[str, float | int]]], None] | None = None,
    curve_callback: Callable[[int, Any], None] | None = None,
    stop_callback: Callable[[int, Any], bool] | None = None,
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
    original_source = image if original_image is None else original_image
    # Reference latents are deliberately encoded under inference_mode to avoid
    # building graphs.  PyTorch inference tensors cannot be saved for a later
    # backward pass, so clone all optimizer inputs outside inference_mode to
    # turn them into ordinary tensors at this boundary.
    original = original_source.to(device=device, dtype=dtype).clone().detach()
    current_source = image if current_image is None else current_image
    current = current_source.to(device=device, dtype=dtype).clone().detach()
    target = target_latent.to(device=device, dtype=dtype).clone().detach()
    records = list(history or [])
    vae.eval().requires_grad_(False)
    started = time.perf_counter()
    stopped_early = False
    completed_step = start_step
    for step in range(start_step + 1, final_step + 1):
        current.requires_grad_(True)
        encoded = vae.encode(current).latent_dist.mode() * (1.0 / vae.config.scaling_factor)
        latent_loss = functional.mse_loss(encoded, target, reduction="mean")
        pixel_loss = functional.mse_loss(current, original, reduction="mean")
        total_loss = latent_loss + lambda_pixel * pixel_loss
        gradient = torch.autograd.grad(total_loss, current, only_inputs=True)[0]
        current = (current - learning_rate * gradient).clamp(-1.0, 1.0).detach()
        completed_step = step
        if step == 1 or step == final_step or step % 50 == 0:
            records.append({"step": step, "latent_loss": float(latent_loss), "pixel_loss": float(pixel_loss), "total_loss": float(total_loss)})
        should_stop = bool(stop_callback and stop_callback(step, current))
        if step % 50 == 0 and checkpoint_callback:
            checkpoint_callback(step, current, records)
        if step % 100 == 0 and curve_callback:
            curve_callback(step, current)
        if should_stop:
            stopped_early = True
            break
    if not stopped_early and completed_step % 100 and curve_callback:
        curve_callback(completed_step, current)
    return OptimizationResult(current, completed_step, records, time.perf_counter() - started, stopped_early)


def optimize_fixed_budget_batch(
    images: Any,
    target_latents: Any,
    vae: Any,
    *,
    lambda_pixels: list[float],
    learning_rate: float,
    final_step: int,
    start_step: int = 0,
    current_images: Any | None = None,
    original_images: Any | None = None,
    histories: list[list[dict[str, float | int]]] | None = None,
    checkpoint_callbacks: list[Callable[[int, Any, list[dict[str, float | int]]], None] | None] | None = None,
    curve_callbacks: list[Callable[[int, Any], None] | None] | None = None,
) -> BatchOptimizationResult:
    """Optimize independent units together while preserving scalar per-sample gradients.

    Each sample loss is reduced over its own elements and the sample losses are
    summed. Therefore the gradient for sample ``i`` is the same gradient that a
    batch-size-one invocation computes, apart from backend floating-point order.
    """
    import torch
    import torch.nn.functional as functional

    if learning_rate != 0.02:
        raise ValueError("formal learning_rate must be 0.02")
    if final_step < start_step or not lambda_pixels or any(value < 0 for value in lambda_pixels):
        raise ValueError("invalid batched optimization budget")
    if getattr(vae, "is_detector", False):
        raise TypeError("A detector cannot be passed as the proxy VAE")
    batch_size = int(images.shape[0])
    if batch_size != len(lambda_pixels) or int(target_latents.shape[0]) != batch_size:
        raise ValueError("batched optimizer inputs have inconsistent batch sizes")
    device = next(vae.parameters()).device
    dtype = next(vae.parameters()).dtype
    original_source = images if original_images is None else original_images
    current_source = images if current_images is None else current_images
    original = original_source.to(device=device, dtype=dtype).clone().detach()
    current = current_source.to(device=device, dtype=dtype).clone().detach()
    targets = target_latents.to(device=device, dtype=dtype).clone().detach()
    records = [list(value) for value in (histories or [[] for _ in range(batch_size)])]
    if len(records) != batch_size:
        raise ValueError("one loss history is required per batch sample")
    checkpoints = checkpoint_callbacks or [None] * batch_size
    curves = curve_callbacks or [None] * batch_size
    if not all(len(values) == batch_size for values in (checkpoints, curves)):
        raise ValueError("one callback slot is required per batch sample")
    lambdas = torch.as_tensor(lambda_pixels, device=device, dtype=dtype)
    vae.eval().requires_grad_(False)
    started = time.perf_counter()
    for step in range(start_step + 1, final_step + 1):
        current.requires_grad_(True)
        encoded = vae.encode(current).latent_dist.mode() * (1.0 / vae.config.scaling_factor)
        latent_losses = functional.mse_loss(encoded, targets, reduction="none").flatten(1).mean(1)
        pixel_losses = functional.mse_loss(current, original, reduction="none").flatten(1).mean(1)
        total_losses = latent_losses + lambdas * pixel_losses
        gradient = torch.autograd.grad(total_losses.sum(), current, only_inputs=True)[0]
        current = (current - learning_rate * gradient).clamp(-1.0, 1.0).detach()
        for index in range(batch_size):
            if step == 1 or step == final_step or step % 50 == 0:
                records[index].append({
                    "step": step,
                    "latent_loss": float(latent_losses[index]),
                    "pixel_loss": float(pixel_losses[index]),
                    "total_loss": float(total_losses[index]),
                })
            if step % 50 == 0 and checkpoints[index]:
                checkpoints[index](step, current[index:index + 1], records[index])
            if step % 100 == 0 and curves[index]:
                curves[index](step, current[index:index + 1])
    if final_step % 100:
        for index, callback in enumerate(curves):
            if callback:
                callback(final_step, current[index:index + 1])
    return BatchOptimizationResult(current, final_step, records, time.perf_counter() - started)
