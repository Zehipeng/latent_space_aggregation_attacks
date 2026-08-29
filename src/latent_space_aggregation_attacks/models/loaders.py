from __future__ import annotations

from pathlib import Path
from typing import Any

from .asset_lock import require_offline


def load_proxy_vae(model: dict[str, Any], *, offline: bool = True) -> Any:
    require_offline(offline)
    from diffusers import AutoencoderKL
    import torch
    dtype = {"float16": torch.float16, "float32": torch.float32, "bfloat16": torch.bfloat16}[model["dtype"]]
    path = Path(model["proxy_vae_path"])
    if not path.exists(): raise FileNotFoundError(path)
    return AutoencoderKL.from_pretrained(path, subfolder=model.get("proxy_vae_subfolder", "vae"), torch_dtype=dtype, local_files_only=True).to(model["device"]).eval().requires_grad_(False)


def load_target_pipeline(model: dict[str, Any], *, offline: bool = True) -> Any:
    require_offline(offline)
    from diffusers import DDIMScheduler, StableDiffusionPipeline
    import torch
    dtype = {"float16": torch.float16, "float32": torch.float32, "bfloat16": torch.bfloat16}[model["dtype"]]
    path = Path(model["target_model_path"])
    if not path.exists(): raise FileNotFoundError(path)
    pipe = StableDiffusionPipeline.from_pretrained(path, torch_dtype=dtype, local_files_only=True, safety_checker=None, requires_safety_checker=False)
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    return pipe.to(model["device"])

