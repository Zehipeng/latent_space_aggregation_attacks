from __future__ import annotations

from typing import Any


def image_to_tensor(image: Any, *, size: int, device: Any, dtype: Any) -> Any:
    """Convert PIL/tensor input to a normalized BCHW tensor without torchvision."""
    import numpy as np
    import torch
    from PIL import Image

    if torch.is_tensor(image):
        value = image.detach()
        if value.ndim == 3:
            value = value.unsqueeze(0)
        return value.to(device=device, dtype=dtype)
    if not isinstance(image, Image.Image):
        raise TypeError(f"Unsupported image type: {type(image)!r}")
    resized = image.convert("RGB").resize((size, size), Image.Resampling.BICUBIC)
    array = np.asarray(resized, dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=dtype)


def tensor_to_pil(image: Any) -> Any:
    import numpy as np
    from PIL import Image

    value = image.detach().float().clamp(-1.0, 1.0)
    if value.ndim == 4:
        value = value[0]
    array = ((value.permute(1, 2, 0).cpu().numpy() + 1.0) * 127.5).round().clip(0, 255)
    return Image.fromarray(array.astype(np.uint8), mode="RGB")


def prepare_random_latents(pipe: Any, seed: int, size: int = 512) -> Any:
    import torch

    generator = torch.Generator(device=pipe.device).manual_seed(int(seed))
    return pipe.prepare_latents(
        1, int(pipe.unet.config.in_channels), size, size,
        pipe.unet.dtype, pipe.device, generator,
    )


def generate_from_latents(pipe: Any, prompt: str, latents: Any, *, steps: int) -> Any:
    return pipe(
        prompt=prompt,
        negative_prompt="",
        guidance_scale=7.5,
        num_inference_steps=int(steps),
        height=512,
        width=512,
        latents=latents.to(device=pipe.device, dtype=pipe.unet.dtype),
    ).images[0]


def invert_image(pipe: Any, image: Any, *, steps: int = 50, size: int = 512) -> Any:
    """DDIM-invert an image using the target pipeline and an empty prompt."""
    import torch
    from diffusers import DDIMInverseScheduler

    original_scheduler = pipe.scheduler
    try:
        scheduler_config = dict(original_scheduler.config)
        # PNDM-only metadata is present in the SD2 scheduler config and causes
        # one warning per inversion when passed to DDIMInverseScheduler.
        scheduler_config.pop("skip_prk_steps", None)
        pipe.scheduler = DDIMInverseScheduler.from_config(scheduler_config)
        tensor = image_to_tensor(image, size=size, device=pipe.device, dtype=pipe.vae.dtype)
        image_latents = (
            pipe.vae.encode(tensor).latent_dist.mode()
            * (1.0 / float(pipe.vae.config.scaling_factor))
        )
        with torch.inference_mode():
            return pipe(
                prompt="",
                latents=image_latents,
                guidance_scale=1.0,
                num_inference_steps=int(steps),
                output_type="latent",
            ).images.float()
    finally:
        pipe.scheduler = original_scheduler


def ncx2_p_value(inverted_fft: Any, target_fft: Any, mask: Any) -> float:
    import torch
    from scipy import stats

    observed_complex = inverted_fft[mask].flatten()
    target_complex = target_fft[mask].flatten()
    observed = torch.cat((observed_complex.real, observed_complex.imag)).float()
    target = torch.cat((target_complex.real, target_complex.imag)).float()
    sigma = observed.std().clamp_min(1e-12)
    noncentrality = (target.square() / sigma.square()).sum().item()
    statistic = (((observed - target) / sigma).square()).sum().item()
    return float(stats.ncx2.cdf(x=statistic, df=target.numel(), nc=noncentrality))
