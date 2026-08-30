from __future__ import annotations
from typing import Any

from .base import Detection
from .runtime import generate_from_latents, invert_image, ncx2_p_value, prepare_random_latents

class RingIDAdapter:
    name = "ringid"
    def __init__(self, config: dict[str, Any]):
        if not config.get("code_revision") or config.get("p_value_threshold") is None:
            raise ValueError("RingID code revision and threshold must be locked")
        self.config = config
        self.pipe = config["pipe"]
        self.threshold = float(config["p_value_threshold"])
        self.radius = int(config.get("radius", 14))
        self.radius_cutoff = int(config.get("radius_cutoff", 3))
        self.ring_value_range = float(config.get("ring_value_range", 64))
        self.generation_steps = int(config.get("generation_steps", 50))
        self.inversion_steps = int(config.get("inversion_steps", 50))
        self._rounder_background = self._build_rounder_background()

    @staticmethod
    def _circle_mask(size: int, radius: int) -> Any:
        import numpy as np
        x0 = y0 = size // 2
        y0 -= 1
        y, x = np.ogrid[:size, :size]
        y = y[::-1]
        return ((x - x0) ** 2 + (y - y0) ** 2 <= radius**2) & (
            ((x > x0) | ((x == x0) & (y > y0))) |
            ((x < x0) | ((x == x0) & (y < y0)))
        )

    @classmethod
    def _ring_mask(cls, size: int, outer: int, inner: int) -> Any:
        return cls._circle_mask(size, outer) & ~cls._circle_mask(size, inner)

    def _build_rounder_background(self) -> Any:
        """Reproduce RingID's USE_ROUNDER_RING=True mask construction."""
        import numpy as np
        import torch
        from torchvision.transforms.functional import rotate

        size = 65
        center = size // 2
        ring_vector = torch.tensor([(200 - index * 4) * (-1) ** index for index in range(self.radius)])
        seed = torch.zeros(1, 1, size, size)
        seed[0, 0, center, center:center + self.radius] = ring_vector
        rotations = torch.zeros(360, size, size)
        rotations[0] = seed
        for angle in range(1, 360):
            rotations[angle] = rotate(seed, angle=angle)
        data = rotations.numpy()
        background = np.zeros((size, size))
        for x in range(size):
            for y in range(size):
                values, counts = np.unique(data[:, x, y], return_counts=True)
                nonzero = values != 0
                if nonzero.any():
                    nz_values, nz_counts = values[nonzero], counts[nonzero]
                    background[x, y] = nz_values[nz_counts.argmax()]
        return background[:64, :64]

    def _official_ring_mask(self, outer: int, inner: int) -> Any:
        import numpy as np
        ring_vector = np.asarray([(200 - index * 4) * (-1) ** index for index in range(self.radius)])
        right_end = 0 if inner - 1 < 0 else inner - 1
        candidates = ring_vector[outer - 1:right_end:-1]
        return np.isin(self._rounder_background, candidates)

    def create_key(self, key_record: dict[str, Any]) -> Any:
        import torch

        seed = int(key_record["watermark_seed"])
        slots = self.radius - self.radius_cutoff
        # Official RingID defaults use two values per one-channel ring slot.
        key_index = seed % (2**slots)
        values = [
            self.ring_value_range if (key_index >> index) & 1 else -self.ring_value_range
            for index in range(slots)
        ]
        shape = (1, int(self.pipe.unet.config.in_channels), 64, 64)
        pattern = torch.zeros(shape, dtype=torch.complex128, device=self.pipe.device)
        ring_channel = 3
        heter_channel = 0
        for offset, outer in enumerate(range(self.radius, self.radius_cutoff, -1)):
            mask = torch.as_tensor(
                self._official_ring_mask(outer, outer - 1), device=self.pipe.device, dtype=torch.float64
            )
            pattern[:, ring_channel].real = (
                (1.0 - mask) * pattern[:, ring_channel].real + mask * values[offset]
            )
            pattern[:, ring_channel].imag = (
                (1.0 - mask) * pattern[:, ring_channel].imag + mask * values[offset]
            )
        region_2d = torch.as_tensor(
            self._official_ring_mask(self.radius, self.radius_cutoff), device=self.pipe.device
        )
        generator = torch.Generator(device=self.pipe.device).manual_seed(seed)
        heter_noise = torch.randn(shape, generator=generator, device=self.pipe.device).float()
        heter_spectrum = torch.fft.fftshift(torch.fft.fft2(heter_noise), dim=(-1, -2))
        pattern[:, heter_channel, region_2d] = heter_spectrum[:, heter_channel, region_2d]
        # Official fix_gt=1 discards the spatial imaginary component before restoring FFT.
        pattern = torch.fft.fftshift(
            torch.fft.fft2(torch.fft.ifft2(torch.fft.ifftshift(pattern, dim=(-1, -2))).real),
            dim=(-1, -2),
        )
        # Official time_shift=1 applies an fftshift in spatial space to ring channels.
        spatial = torch.fft.ifft2(torch.fft.ifftshift(pattern[:, ring_channel:ring_channel + 1], dim=(-1, -2)))
        shifted = torch.fft.fftshift(spatial, dim=(-1, -2))
        pattern[:, ring_channel:ring_channel + 1] = torch.fft.fftshift(
            torch.fft.fft2(shifted), dim=(-1, -2)
        )
        mask = torch.zeros(shape, dtype=torch.bool, device=self.pipe.device)
        mask[:, heter_channel] = region_2d
        mask[:, ring_channel] = region_2d
        return {"pattern": pattern, "mask": mask, "key_index": int(key_index), "seed": seed}

    def generate(self, prompt: str, key: Any, seed: int) -> Any:
        import torch
        initial = prepare_random_latents(self.pipe, seed).float()
        spectrum = torch.fft.fftshift(torch.fft.fft2(initial), dim=(-1, -2))
        spectrum[key["mask"]] = key["pattern"][key["mask"]]
        latents = torch.fft.ifft2(torch.fft.ifftshift(spectrum, dim=(-1, -2))).real
        return generate_from_latents(self.pipe, prompt, latents, steps=self.generation_steps)

    def detect(self, image: Any, key: Any) -> Detection:
        import torch
        inverted = invert_image(self.pipe, image, steps=self.inversion_steps)
        spectrum = torch.fft.fftshift(torch.fft.fft2(inverted), dim=(-1, -2))
        score = ncx2_p_value(spectrum, key["pattern"], key["mask"])
        return Detection(score=score, accepted=score <= self.threshold, score_name="p_value")
