from __future__ import annotations

from typing import Any


class TreeRingAdapter:
    name = "tree_ring"
    def __init__(self, config: dict[str, Any]): self.config = config
    def create_key(self, key_record: dict[str, Any]) -> Any:
        raise RuntimeError("Tree-Ring runtime requires prepared offline assets; run prepare_offline_assets.py first")
    def generate(self, prompt: str, key: Any, seed: int) -> Any:
        raise RuntimeError("Tree-Ring GPU backend is activated by the offline asset adapter")
    def detect(self, image: Any, key: Any) -> Any:
        raise RuntimeError("Detector is available only to P0/evaluation processes")

