from __future__ import annotations

from typing import Any


def clean_mean(clean_latents: Any, n_clean: int) -> Any:
    if n_clean not in {1, 5, 25}:
        raise ValueError("N_clean must be one of 1, 5, 25")
    if int(clean_latents.shape[0]) < n_clean:
        raise ValueError(f"Only {clean_latents.shape[0]} clean latents for N_clean={n_clean}")
    return clean_latents[:n_clean].float().mean(dim=0, keepdim=True)


def direction(watermarked_latent: Any, clean_latents: Any, n_clean: int) -> Any:
    if int(watermarked_latent.shape[0]) != 1:
        raise ValueError("Exactly one watermarked latent is required")
    return watermarked_latent.float() - clean_mean(clean_latents, n_clean)


def removal_target(
    watermarked_latent: Any, clean_latents: Any, n_clean: int, beta: float,
) -> Any:
    if beta not in {1.0, 1.5, 2.0}:
        raise ValueError("beta must be one of 1.0, 1.5, 2.0")
    return watermarked_latent.float() - beta * direction(
        watermarked_latent, clean_latents, n_clean,
    )

def forgery_target(
    clean_source_latent: Any, watermarked_latent: Any,
    clean_latents: Any, n_clean: int, beta: float = 1.5,
) -> Any:
    if int(clean_source_latent.shape[0]) != 1:
        raise ValueError("Forgery requires one clean source latent")
    if beta != 1.5:
        raise ValueError("Forgery beta is frozen at 1.5")
    return clean_source_latent.float() + beta * direction(
        watermarked_latent, clean_latents, n_clean,
    )


__all__ = ("clean_mean", "direction", "removal_target", "forgery_target")
