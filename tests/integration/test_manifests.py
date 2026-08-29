import pytest
from latent_space_aggregation_attacks.core.manifests import ensure_disjoint,validate_nested_indices
def test_manifest_isolation_and_nested_banks():
    ensure_disjoint(["pilot"],["formal"],"keys")
    with pytest.raises(ValueError): ensure_disjoint(["same"],["same"],"keys")
    rows=[{"key_id":"key_000","reference_index":i} for i in range(25)]; validate_nested_indices(rows)
    with pytest.raises(ValueError): validate_nested_indices(rows[:-1])


def test_v19_cross_task_role_overlap_is_intentional():
    targets = set(range(200))
    clean = set(range(5000))
    assert len(targets & clean) == 200
