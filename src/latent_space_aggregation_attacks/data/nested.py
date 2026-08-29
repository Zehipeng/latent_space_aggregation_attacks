from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def nested_prefix(values: Sequence[T], n: int) -> list[T]:
    if n not in {1, 5, 25}:
        raise ValueError("N must be one of 1, 5, 25")
    if len(values) < 25:
        raise ValueError("A pre-registered bank must contain at least 25 ordered items")
    return list(values[:n])


def key_ids(count: int, *, pilot: bool = False) -> list[str]:
    expected = 100 if pilot else 200
    if count != expected:
        raise ValueError(f"Expected {expected} keys")
    prefix = "pilot_key" if pilot else "key"
    return [f"{prefix}_{index:03d}" for index in range(count)]

