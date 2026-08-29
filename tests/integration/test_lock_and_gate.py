import pytest
from latent_space_aggregation_attacks.core.locking import UnitLock
from latent_space_aggregation_attacks.core.gates import SmokeSignature,require_full_run_gate
def test_worker_lock_is_exclusive(tmp_path):
    lock=tmp_path/"unit.lock"
    with UnitLock(lock):
        with pytest.raises(RuntimeError):
            with UnitLock(lock): pass
    assert not lock.exists()
def test_matching_smoke_is_required():
    s=SmokeSignature("v","c","g","a","s"); require_full_run_gate(s,s,True)
    with pytest.raises(RuntimeError): require_full_run_gate(s,None,False)
