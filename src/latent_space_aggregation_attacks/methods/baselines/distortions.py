from __future__ import annotations

from typing import Any


def apply_distortion(image: Any, name: str, *, seed: int) -> Any:
    """Apply one protocol-locked E6 transform to a PIL RGB image."""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    source = image.convert("RGB")
    if name == "jpeg25":
        buffer = io.BytesIO(); source.save(buffer, format="JPEG", quality=25); buffer.seek(0)
        with Image.open(buffer) as decoded:
            return decoded.convert("RGB").copy()
    if name == "crop75":
        rng = np.random.default_rng(seed)
        side = round(512 * (0.75 ** 0.5))
        left = int(rng.integers(0, 512 - side + 1)); top = int(rng.integers(0, 512 - side + 1))
        return source.crop((left, top, left + side, top + side)).resize((512, 512), Image.Resampling.BICUBIC)
    if name == "resize384":
        return source.resize((384, 384), Image.Resampling.BICUBIC).resize((512, 512), Image.Resampling.BICUBIC)
    if name == "gaussian_blur8":
        return source.filter(ImageFilter.GaussianBlur(radius=8.0))
    if name == "gaussian_noise01":
        rng = np.random.default_rng(seed)
        array = np.asarray(source, dtype=np.float32) / 255.0
        noisy = np.clip(array + rng.normal(0.0, 0.1, array.shape), 0.0, 1.0)
        return Image.fromarray(np.rint(noisy * 255).astype(np.uint8), "RGB")
    raise ValueError(f"Unknown distortion: {name}")


def matched_l2_noise(image: Any, attacked: Any, *, seed: int) -> tuple[Any, float, float]:
    import numpy as np
    original = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    target = np.asarray(attacked.convert("RGB"), dtype=np.float32) / 255.0
    target_l2 = float(np.linalg.norm((target - original).reshape(-1)))
    noise = np.random.default_rng(seed).normal(size=original.shape).astype(np.float32)
    noise *= target_l2 / max(float(np.linalg.norm(noise.reshape(-1))), 1e-12)
    result = np.clip(original + noise, 0.0, 1.0)
    actual = result - original
    from PIL import Image
    output = Image.fromarray(np.rint(result * 255).astype(np.uint8), "RGB")
    return output, float(np.linalg.norm(actual.reshape(-1))), float(np.abs(actual).max())

