from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Detection:
    score: float
    accepted: bool
    score_name: str


class WatermarkAdapter(Protocol):
    name: str
    def create_key(self, key_record: dict[str, Any]) -> Any: ...
    def generate(self, prompt: str, key: Any, seed: int) -> Any: ...
    def invert(self, image: Any) -> Any: ...
    def detect_inverted(self, inverted: Any, key: Any) -> Detection: ...
    def detect(self, image: Any, key: Any) -> Detection: ...


def registered_adapter(name: str, config: dict[str, Any]) -> WatermarkAdapter:
    if name == "tree_ring":
        from .tree_ring import TreeRingAdapter
        return TreeRingAdapter(config)
    if name == "ringid":
        from .ringid import RingIDAdapter
        return RingIDAdapter(config)
    if name == "gaussian_shading":
        from .gaussian_shading import GaussianShadingAdapter
        return GaussianShadingAdapter(config)
    raise ValueError(name)
