from __future__ import annotations

from typing import Any

from .base import Detection
from .runtime import generate_from_latents, invert_image, invert_images, ncx2_p_value, prepare_random_latents


class TreeRingAdapter:
    name = "tree_ring"
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.pipe = config["pipe"]
        self.radius = int(config["radius"])
        self.channel = int(config["channel"])
        self.threshold = float(config["p_value_threshold"])
        self.generation_steps = int(config.get("generation_steps", 50))
        self.inversion_steps = int(config.get("inversion_steps", 50))

    @staticmethod
    def _circle_mask(size: int, radius: int) -> Any:
        import numpy as np
        center = size // 2
        y, x = np.ogrid[:size, :size]
        y = y[::-1]
        return (x - center) ** 2 + (y - center) ** 2 <= radius**2

    def create_key(self, key_record: dict[str, Any]) -> Any:
        import torch
        seed = int(key_record["watermark_seed"])
        initial = prepare_random_latents(self.pipe, seed).float()
        key = torch.fft.fftshift(torch.fft.fft2(initial), dim=(-1, -2))
        source = key.clone()
        for radius in range(key.shape[-1] // 2, 0, -1):
            ring = torch.as_tensor(self._circle_mask(key.shape[-1], radius), device=self.pipe.device)
            for channel in range(key.shape[1]):
                key[:, channel, ring] = source[0, channel, 0, radius]
        mask = torch.zeros_like(initial, dtype=torch.bool)
        mask[:, self.channel] = torch.as_tensor(
            self._circle_mask(initial.shape[-1], self.radius), device=self.pipe.device
        )
        return {"pattern": key, "mask": mask, "seed": seed}

    def generate(self, prompt: str, key: Any, seed: int) -> Any:
        import torch
        initial = prepare_random_latents(self.pipe, seed).float()
        spectrum = torch.fft.fftshift(torch.fft.fft2(initial), dim=(-1, -2))
        spectrum[key["mask"]] = key["pattern"][key["mask"]]
        latents = torch.fft.ifft2(torch.fft.ifftshift(spectrum, dim=(-1, -2))).real
        return generate_from_latents(self.pipe, prompt, latents, steps=self.generation_steps)

    def invert(self, image: Any) -> Any:
        return invert_image(self.pipe, image, steps=self.inversion_steps)

    def invert_many(self, images: list[Any]) -> Any:
        return invert_images(self.pipe, images, steps=self.inversion_steps)

    def detect_inverted(self, inverted: Any, key: Any) -> Detection:
        import torch
        spectrum = torch.fft.fftshift(torch.fft.fft2(inverted), dim=(-1, -2))
        score = ncx2_p_value(spectrum, key["pattern"], key["mask"])
        return Detection(score=score, accepted=score <= self.threshold, score_name="p_value")

    def detect(self, image: Any, key: Any) -> Detection:
        return self.detect_inverted(self.invert(image), key)
