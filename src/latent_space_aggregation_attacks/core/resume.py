from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_save, atomic_write_text
from .hashing import sha256_file


@dataclass
class ResumeState:
    unit_id: str
    step: int
    image_tensor: Any
    loss_history: list[dict[str, float | int]]
    rng_state: dict[str, Any]
    timing: dict[str, float]
    input_hash: str
    resolved_config_hash: str
    protocol_version: str
    git_sha: str


def save_resume_state(path: str | Path, state: ResumeState) -> str:
    atomic_save(path, state, lambda value, handle: pickle.dump(value, handle, protocol=5))
    checksum = sha256_file(path)
    atomic_write_text(f"{path}.sha256", checksum + "\n")
    return checksum


def load_resume_state(
    path: str | Path,
    *,
    expected_unit_id: str,
    input_hash: str,
    resolved_config_hash: str,
    protocol_version: str,
    git_sha: str,
) -> ResumeState:
    source = Path(path)
    checksum_path = Path(f"{path}.sha256")
    if not source.is_file() or not checksum_path.is_file():
        raise FileNotFoundError(source)
    expected_checksum = checksum_path.read_text(encoding="ascii").strip()
    if sha256_file(source) != expected_checksum:
        raise ValueError("Resume checksum mismatch")
    try:
        with source.open("rb") as handle:
            state = pickle.load(handle)
    except Exception as exc:
        raise ValueError("Corrupt resume state") from exc
    if not isinstance(state, ResumeState):
        raise ValueError("Invalid resume payload type")
    expected = (expected_unit_id, input_hash, resolved_config_hash, protocol_version, git_sha)
    recorded = (state.unit_id, state.input_hash, state.resolved_config_hash, state.protocol_version, state.git_sha)
    if recorded != expected:
        raise ValueError("Resume identity/hash mismatch")
    return state
