from __future__ import annotations

from typing import Any


def _torch() -> Any:
    import torch
    return torch


def fp32_mean(latents: Any) -> Any:
    torch = _torch()
    working = latents.detach().float()
    if working.ndim < 2 or working.shape[0] < 1:
        raise ValueError("latents must have shape [N, ...]")
    if not torch.isfinite(working).all():
        raise ValueError("latents contain non-finite values")
    # Keep the batch dimension because VAE.encode returns [B,C,H,W].  Dropping
    # it silently broadcasts the target during MSE and hides shape mistakes.
    return working.mean(dim=0, keepdim=True)


def forgery_target(reference_latents: Any) -> Any:
    return fp32_mean(reference_latents)


def removal_target(target_latent: Any, watermarked_latents: Any, clean_latents: Any, beta: float) -> Any:
    if beta not in {0.5, 1.0, 2.0}:
        raise ValueError("beta must be one of 0.5, 1.0, 2.0")
    return target_latent.detach().float() - beta * (
        fp32_mean(watermarked_latents) - fp32_mean(clean_latents)
    )
