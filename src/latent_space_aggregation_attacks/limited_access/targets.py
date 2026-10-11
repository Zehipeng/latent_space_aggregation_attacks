from __future__ import annotations

from typing import Any


def clean_mean(clean_latents: Any) -> Any:
    if int(clean_latents.shape[0]) != 5:
        raise ValueError("exactly five clean latents are required")
    return clean_latents.float().mean(dim=0, keepdim=True)


def direction(watermarked_latent: Any, clean_latents: Any) -> Any:
    if int(watermarked_latent.shape[0]) != 1:
        raise ValueError("exactly one watermarked latent is required")
    return watermarked_latent.float() - clean_mean(clean_latents)


def removal_target(watermarked_latent: Any, clean_latents: Any, beta: float = 1.5) -> Any:
    if beta != 1.5:
        raise ValueError("limited-access beta is frozen at 1.5")
    return watermarked_latent.float() - beta * direction(watermarked_latent, clean_latents)


def forgery_target(clean_source_latent: Any, watermarked_latent: Any, clean_latents: Any, beta: float = 1.5) -> Any:
    if int(clean_source_latent.shape[0]) != 1:
        raise ValueError("forgery requires the first clean image latent")
    if beta != 1.5:
        raise ValueError("limited-access beta is frozen at 1.5")
    return clean_source_latent.float() + beta * direction(watermarked_latent, clean_latents)
