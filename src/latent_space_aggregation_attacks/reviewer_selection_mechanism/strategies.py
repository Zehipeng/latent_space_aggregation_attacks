from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Iterable

from ..core.seeds import derive_seed


@dataclass(frozen=True)
class SelectionStrategy:
    id: str
    verified_only: bool
    strategy_seed: int | None


def strategy_registry() -> tuple[SelectionStrategy, ...]:
    return (
        SelectionStrategy("random_verified_25_seed17", True, 17),
        SelectionStrategy("random_verified_25_seed29", True, 29),
        SelectionStrategy("random_verified_25_seed43", True, 43),
        SelectionStrategy("unfiltered_ordered_25", False, None),
    )


def validate_candidate_bank(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    bank = list(rows)
    indices = [int(row["candidate_index"]) for row in bank]
    if len(bank) != 64 or sorted(indices) != list(range(64)):
        raise ValueError("candidate bank must contain each index 0--63 exactly once")
    return sorted(bank, key=lambda row: int(row["candidate_index"]))


def select_references(
    rows: Iterable[dict[str, Any]],
    strategy: SelectionStrategy,
    *,
    model_setting: str,
    watermark: str,
    key_id: str,
    count: int = 25,
) -> list[dict[str, Any]]:
    bank = validate_candidate_bank(rows)
    if count != 25:
        raise ValueError("E2 reference count is frozen at 25")
    if not strategy.verified_only:
        return bank[:count]
    accepted = [row for row in bank if _bool(row["accepted"])]
    if len(accepted) < count:
        raise ValueError(
            f"{model_setting}/{watermark}/{key_id} has only "
            f"{len(accepted)} accepted candidates"
        )
    assert strategy.strategy_seed is not None
    seed = derive_seed(
        "reviewer_selection", strategy.strategy_seed,
        model_setting, watermark, key_id,
    )
    selected = random.Random(seed).sample(accepted, count)
    return sorted(selected, key=lambda row: int(row["candidate_index"]))


def pool_feasibility(rows: Iterable[dict[str, Any]]) -> dict[int, bool]:
    bank = validate_candidate_bank(rows)
    return {
        prefix: sum(_bool(row["accepted"]) for row in bank[:prefix]) >= 25
        for prefix in (25, 32, 48, 64)
    }


def clean_subsets(
    rows: Iterable[dict[str, Any]],
    *,
    model_setting: str,
    watermark: str,
    key_id: str,
) -> dict[int, list[dict[str, Any]]]:
    clean = sorted(list(rows), key=lambda row: int(row["clean_index"]))
    if len(clean) != 25 or [int(row["clean_index"]) for row in clean] != list(range(25)):
        raise ValueError("clean bank must contain each index 0--24 exactly once")
    output = {}
    for strategy_seed in (101, 103, 107, 109, 113):
        seed = derive_seed(
            "reviewer_clean_subset", strategy_seed,
            model_setting, watermark, key_id,
        )
        chosen = random.Random(seed).sample(clean, 5)
        output[strategy_seed] = sorted(
            chosen, key=lambda row: int(row["clean_index"]),
        )
    return output


def shuffled_key(key_id: str, key_ids: list[str]) -> str:
    if len(key_ids) < 2 or len(set(key_ids)) != len(key_ids):
        raise ValueError("shuffled-key control requires at least two unique keys")
    try:
        index = key_ids.index(key_id)
    except ValueError as exc:
        raise ValueError(f"unknown key: {key_id}") from exc
    return key_ids[(index + 1) % len(key_ids)]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ValueError(f"invalid boolean: {value!r}")
