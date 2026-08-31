from __future__ import annotations

import hashlib
import os
import random
from typing import Any

import numpy as np

from latent_space_aggregation_attacks import MASTER_SEED, SEED_NAMESPACE_VERSION

NAMESPACES = frozenset(
    {"generation", "watermark_key", "data_order", "transform", "budget_pilot", "worker"}
)

# This must be present before CUDA creates a cuBLAS workspace. ``setdefault``
# preserves any explicitly configured environment value.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


def derive_seed(namespace: str, *identifiers: object) -> int:
    if namespace not in NAMESPACES:
        raise ValueError(f"Unknown seed namespace: {namespace}")
    identifier_text = "|".join(str(value) for value in identifiers)
    payload = f"{SEED_NAMESPACE_VERSION}|{MASTER_SEED}|{namespace}|{identifier_text}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % (2**63 - 1)


def seed_runtime(seed: int, torch_module: Any | None = None) -> dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed % 2**32)
    state: dict[str, Any] = {"seed": seed}
    if torch_module is not None:
        torch_module.manual_seed(seed)
        if torch_module.cuda.is_available():
            torch_module.cuda.manual_seed_all(seed)
        state["generator"] = torch_module.Generator().manual_seed(seed)
    return state


def configure_torch_determinism(torch_module: Any) -> dict[str, Any]:
    """Lock the CUDA math backends used by iterative image optimization."""
    torch_module.use_deterministic_algorithms(True)
    torch_module.backends.cudnn.benchmark = False
    torch_module.backends.cudnn.deterministic = True
    torch_module.backends.cudnn.allow_tf32 = False
    torch_module.backends.cuda.matmul.allow_tf32 = False
    return {
        "deterministic_algorithms": torch_module.are_deterministic_algorithms_enabled(),
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"],
        "cudnn_benchmark": bool(torch_module.backends.cudnn.benchmark),
        "cudnn_deterministic": bool(torch_module.backends.cudnn.deterministic),
        "cudnn_allow_tf32": bool(torch_module.backends.cudnn.allow_tf32),
        "cuda_matmul_allow_tf32": bool(torch_module.backends.cuda.matmul.allow_tf32),
    }


def capture_rng_state(torch_module: Any | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {"python": random.getstate(), "numpy": np.random.get_state()}
    if torch_module is not None:
        state["torch_cpu"] = torch_module.get_rng_state()
        state["torch_cuda"] = (
            torch_module.cuda.get_rng_state_all() if torch_module.cuda.is_available() else []
        )
    return state


def restore_rng_state(state: dict[str, Any], torch_module: Any | None = None) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    if torch_module is not None and "torch_cpu" in state:
        torch_module.set_rng_state(state["torch_cpu"])
        if torch_module.cuda.is_available() and state.get("torch_cuda"):
            torch_module.cuda.set_rng_state_all(state["torch_cuda"])
