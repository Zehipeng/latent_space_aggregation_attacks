import pytest
import json
from latent_space_aggregation_attacks.core.locking import UnitLock
from latent_space_aggregation_attacks.core.gates import SmokeSignature,require_full_run_gate
from latent_space_aggregation_attacks.core.hashing import stable_hash
from latent_space_aggregation_attacks.formal.orchestrator import validate_batch_equivalence,validate_tree_ring_regression
def test_worker_lock_is_exclusive(tmp_path):
    lock=tmp_path/"unit.lock"
    with UnitLock(lock):
        with pytest.raises(RuntimeError):
            with UnitLock(lock): pass
    assert not lock.exists()
def test_matching_smoke_is_required():
    s=SmokeSignature("v","c","g","a","s"); require_full_run_gate(s,s,True)
    with pytest.raises(RuntimeError): require_full_run_gate(s,None,False)

def test_stale_worker_lock_is_recovered(tmp_path):
    lock=tmp_path/"unit.lock"
    lock.write_text("999999999",encoding="ascii")
    with UnitLock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_tree_ring_regression_is_bound_to_run_identity(tmp_path, monkeypatch):
    import latent_space_aggregation_attacks.formal.orchestrator as orchestrator
    monkeypatch.setattr(orchestrator, "git_sha", lambda _: "abc123")
    config = {"resolved_config_hash": "config-hash"}
    assets = {"schema_version": 2, "assets": []}
    report = {
        "status": "PASSED", "protocol_version": "formal_protocol_v1.17",
        "git_sha": "abc123", "source_resolved_config_hash": "config-hash",
        "assets_lock_hash": stable_hash(assets),
    }
    path = tmp_path / "regression.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert validate_tree_ring_regression(
        path, config=config, assets_lock=assets, project_root=tmp_path,
    ) == report
    report["git_sha"] = "stale"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match"):
        validate_tree_ring_regression(path, config=config, assets_lock=assets, project_root=tmp_path)


def test_batch_equivalence_gate_is_bound_to_batch_settings(tmp_path, monkeypatch):
    import latent_space_aggregation_attacks.formal.orchestrator as orchestrator
    monkeypatch.setattr(orchestrator, "git_sha", lambda _: "abc123")
    batching = {
        "attack_batch_size": 4, "inversion_batch_size": 8,
        "reference_encode_batch_size": 8, "require_equivalence_gate": True,
    }
    config = {"resolved_config_hash": "config-hash", "validated_batching": batching}
    assets = {"schema_version": 2, "assets": []}
    report = {
        "status": "PASSED", "protocol_version": "formal_protocol_v1.17",
        "git_sha": "abc123", "source_resolved_config_hash": "config-hash",
        "assets_lock_hash": stable_hash(assets), "validated_batching": batching,
        "failures": [],
    }
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert validate_batch_equivalence(
        path, config=config, assets_lock=assets, project_root=tmp_path,
    ) == report
    report["validated_batching"] = {**batching, "attack_batch_size": 1}
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match"):
        validate_batch_equivalence(path, config=config, assets_lock=assets, project_root=tmp_path)
