from __future__ import annotations

from typing import Any, Literal


def estimate_pixel_direction(watermarked_images: Any, clean_images: Any) -> Any:
    if watermarked_images.shape != clean_images.shape or watermarked_images.shape[0] < 1:
        raise ValueError("Watermarked and clean non-paired banks must have equal [N,...] shape")
    return watermarked_images.detach().float().mean(dim=0) - clean_images.detach().float().mean(dim=0)


def apply_pixel_direction(image: Any, direction: Any, task: Literal["forgery", "removal"], gamma: float = 1.0) -> Any:
    if gamma != 1.0:
        raise ValueError("Formal Simple Averaging fixes gamma=1")
    sign = 1.0 if task == "forgery" else -1.0
    return (image.detach().float() + sign * direction.detach().float()).clamp(0.0, 1.0)

