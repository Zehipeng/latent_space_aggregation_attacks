from __future__ import annotations
from typing import Any

class RingIDAdapter:
    name = "ringid"
    def __init__(self, config: dict[str, Any]):
        if not config.get("code_revision") or not config.get("threshold"):
            raise ValueError("RingID code revision and threshold must be locked")
    def create_key(self, key_record: dict[str, Any]) -> Any: raise RuntimeError("Offline RingID backend not prepared")
    def generate(self, prompt: str, key: Any, seed: int) -> Any: raise RuntimeError("Offline RingID backend not prepared")
    def detect(self, image: Any, key: Any) -> Any: raise RuntimeError("Detector is evaluation-only")

