from __future__ import annotations

from typing import Any


def jain_forgery_target(reference_latents: Any) -> Any:
    if reference_latents.shape[0] < 1:
        raise ValueError("Jain requires reference index 0")
    return reference_latents[0:1].detach().float()


def jain_removal_mean_image(image: Any) -> Any:
    import torch
    return torch.full_like(image, image.detach().mean())
