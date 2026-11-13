from pathlib import Path

import pytest

from latent_space_aggregation_attacks.reviewer_single_reference.conditions import (
    condition_registry,
    validate_registry,
)
from latent_space_aggregation_attacks.reviewer_single_reference.config import (
    compatibility_hash,
    load_config,
)


ROOT = Path(__file__).resolve().parents[2]


def test_condition_matrix_is_complete_and_deduplicated() -> None:
    conditions = condition_registry()
    validate_registry(conditions)
    assert len(conditions) == 72
    assert len({condition.id for condition in conditions}) == 72
    assert {condition.N_watermarked for condition in conditions} == {1}
    counts = {}
    for condition in conditions:
        key = (condition.model_setting, condition.watermark, condition.task)
        counts[key] = counts.get(key, 0) + 1
    assert {count for (*_, task), count in counts.items() if task == "forgery"} == {5}
    assert {count for (*_, task), count in counts.items() if task == "removal"} == {7}


def test_smoke_and_formal_configs_share_experiment_identity() -> None:
    smoke = load_config(
        ROOT / "configs/additional/reviewer_single_reference_smoke_2key.yaml"
    )
    formal = load_config(
        ROOT / "configs/additional/reviewer_single_reference_formal_200key.yaml"
    )
    assert smoke["key_count"] == 2
    assert formal["key_count"] == 200
    assert compatibility_hash(smoke) == compatibility_hash(formal)


def test_single_reference_targets() -> None:
    torch = pytest.importorskip("torch")
    from latent_space_aggregation_attacks.reviewer_single_reference.targets import (
        forgery_target,
        removal_target,
    )

    watermarked = torch.tensor([[[[4.0]]]])
    clean = torch.tensor([[[[1.0]]], [[[3.0]]], [[[5.0]]], [[[7.0]]], [[[9.0]]]])
    source = torch.tensor([[[[10.0]]]])
    assert removal_target(watermarked, clean, 1, 1.0).item() == 1.0
    assert removal_target(watermarked, clean, 5, 1.5).item() == 5.5
    assert forgery_target(source, watermarked, clean, 1).item() == 14.5
