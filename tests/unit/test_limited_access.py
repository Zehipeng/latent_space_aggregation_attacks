from pathlib import Path

import numpy as np
import pytest

from latent_space_aggregation_attacks.limited_access.config import compatibility_hash, load_config
from latent_space_aggregation_attacks.limited_access.evaluate import _success
from latent_space_aggregation_attacks.limited_access.targets import direction, forgery_target, removal_target


class Tensor:
    def __init__(self, value): self.value = np.asarray(value, dtype=np.float32); self.shape = self.value.shape
    def float(self): return self
    def mean(self, dim=0, keepdim=False): return Tensor(self.value.mean(axis=dim, keepdims=keepdim))
    def __sub__(self, other): return Tensor(self.value - other.value)
    def __add__(self, other): return Tensor(self.value + other.value)
    def __mul__(self, scalar): return Tensor(self.value * scalar)
    __rmul__ = __mul__


def test_bidirectional_targets_use_one_watermarked_and_five_clean_latents():
    watermarked = Tensor([[[[10.0]]]])
    clean = Tensor([[[[value]]] for value in range(1, 6)])
    clean_source = Tensor([[[[1.0]]]])
    np.testing.assert_allclose(direction(watermarked, clean).value, [[[[7.0]]]])
    np.testing.assert_allclose(removal_target(watermarked, clean).value, [[[[-0.5]]]])
    np.testing.assert_allclose(forgery_target(clean_source, watermarked, clean).value, [[[[11.5]]]])


def test_config_locks_scope_and_smoke_formal_compatibility():
    root = Path(__file__).resolve().parents[2]
    smoke = load_config(root / "configs/additional/limited_access_smoke_2key.yaml")
    formal = load_config(root / "configs/additional/limited_access_formal_200key.yaml")
    assert compatibility_hash(smoke) == compatibility_hash(formal)
    assert smoke["metrics"] == ["ASR", "LPIPS", "SSIM", "PSNR", "FID", "Time"]
    assert smoke["watermarked_reference_count"] == 1
    assert smoke["clean_reference_count"] == 5


def test_target_rejects_wrong_counts_and_beta():
    with pytest.raises(ValueError): direction(Tensor([[[[1.0]]], [[[2.0]]]]), Tensor([[[[1.0]]]] * 5))
    with pytest.raises(ValueError): removal_target(Tensor([[[[1.0]]]]), Tensor([[[[1.0]]]] * 4))
    with pytest.raises(ValueError): removal_target(Tensor([[[[1.0]]]]), Tensor([[[[1.0]]]] * 5), 1.0)


def test_detection_boundaries_match_registered_semantics():
    assert _success("tree_ring", "removal", True, True, 0.05, 0.05) == (True, True, True)
    assert _success("tree_ring", "forgery", False, True, 0.01, 0.05) == (True, True, False)
    assert _success("gaussian_shading", "removal", True, False, 0.60, 0.6484375) == (True, True, False)


def test_attack_module_has_no_detector_or_watermark_import():
    root = Path(__file__).resolve().parents[2]
    source = (root / "src/latent_space_aggregation_attacks/limited_access/attack.py").read_text(encoding="utf-8")
    assert "watermarks" not in source
    assert "load_target_pipeline" not in source
    assert "adapter.detect" not in source
