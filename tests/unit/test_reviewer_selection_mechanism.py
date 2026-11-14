from pathlib import Path

import pytest

from latent_space_aggregation_attacks.reviewer_selection_mechanism.conditions import (
    condition_registry,
    validate_registry,
)
from latent_space_aggregation_attacks.reviewer_selection_mechanism.config import (
    compatibility_hash,
    load_config,
)
from latent_space_aggregation_attacks.reviewer_selection_mechanism.strategies import (
    clean_subsets,
    pool_feasibility,
    select_references,
    shuffled_key,
    strategy_registry,
)


ROOT = Path(__file__).resolve().parents[2]


def _bank() -> list[dict[str, object]]:
    return [
        {"candidate_index": index, "accepted": index % 5 != 0}
        for index in range(64)
    ]


def test_condition_matrix_is_complete() -> None:
    conditions = condition_registry()
    validate_registry(conditions)
    assert len(conditions) == 48
    assert len({condition.id for condition in conditions}) == 48
    assert len(conditions) * 2 == 96
    assert len(conditions) * 200 == 9600


def test_selection_is_deterministic_and_separated() -> None:
    strategies = strategy_registry()
    first = select_references(
        _bank(), strategies[0], model_setting="same", watermark="tree_ring",
        key_id="key_000",
    )
    again = select_references(
        reversed(_bank()), strategies[0], model_setting="same",
        watermark="tree_ring", key_id="key_000",
    )
    other = select_references(
        _bank(), strategies[1], model_setting="same", watermark="tree_ring",
        key_id="key_000",
    )
    assert [row["candidate_index"] for row in first] == [
        row["candidate_index"] for row in again
    ]
    assert {row["candidate_index"] for row in first} != {
        row["candidate_index"] for row in other
    }
    unfiltered = select_references(
        _bank(), strategies[-1], model_setting="same", watermark="tree_ring",
        key_id="key_000",
    )
    assert [row["candidate_index"] for row in unfiltered] == list(range(25))


def test_selection_rejects_incomplete_or_underfilled_banks() -> None:
    with pytest.raises(ValueError, match="0--63"):
        select_references(
            _bank()[:-1], strategy_registry()[0], model_setting="same",
            watermark="tree_ring", key_id="key_000",
        )
    underfilled = _bank()
    for row in underfilled:
        row["accepted"] = int(row["candidate_index"]) < 24
    with pytest.raises(ValueError, match="only 24"):
        select_references(
            underfilled, strategy_registry()[0], model_setting="same",
            watermark="tree_ring", key_id="key_000",
        )


def test_pool_clean_subset_and_shuffled_key_controls() -> None:
    feasibility = pool_feasibility(_bank())
    assert set(feasibility) == {25, 32, 48, 64}
    clean = [{"clean_index": index} for index in range(25)]
    subsets = clean_subsets(
        clean, model_setting="same", watermark="tree_ring", key_id="key_000",
    )
    assert set(subsets) == {101, 103, 107, 109, 113}
    assert all(len(rows) == 5 for rows in subsets.values())
    keys = ["key_000", "key_001", "key_002"]
    assert shuffled_key("key_000", keys) == "key_001"
    assert shuffled_key("key_002", keys) == "key_000"


def test_smoke_and_formal_configs_are_compatible() -> None:
    smoke = load_config(
        ROOT / "configs/additional/reviewer_selection_mechanism_smoke_2key.yaml"
    )
    formal = load_config(
        ROOT / "configs/additional/reviewer_selection_mechanism_formal_200key.yaml"
    )
    assert compatibility_hash(smoke) == compatibility_hash(formal)
