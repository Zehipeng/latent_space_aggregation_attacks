import numpy as np
import pytest
import csv
import json
from PIL import Image
from scipy.linalg import sqrtm

from latent_space_aggregation_attacks.formal.attack import _matched_noise
from latent_space_aggregation_attacks.formal.evaluate import _cleanup_validated_spools, _detect_key_bank, _detect_key_bank_many, _fid
from latent_space_aggregation_attacks.formal.common import frozen_trajectory_steps
from latent_space_aggregation_attacks.formal.orchestrator import _eta_report
from latent_space_aggregation_attacks.models.asset_lock import validate_formal_assets


def _asset(name, revision):
    return {"name": name, "revision": revision, "path": f"/{name}"}


def test_formal_asset_gate_rejects_legacy_manifest_names():
    payload = {"assets": [
        _asset("stable-diffusion-v1-4", "133a221b8aa7292a167afc5127cb63fb5005638b"),
        _asset("stable-diffusion-2-base", "f5bc1bd97485577aa0b946fa8a9004e2ec147402"),
        _asset("tree-ring-watermark", "3015283d9cf82e90b628f02ad2121bd37408ca9a"),
        _asset("RingID", "45631a59aecd7d63ccdb640aaaf3e616fdb89fb9"),
        _asset("Gaussian-Shading", "09c678fadc7545acf7be12647ddf2a5e66f6a9dc"),
        _asset("formal-protocol-v1.9-prompt-manifest", "formal_protocol_v1.9"),
        _asset("formal-protocol-v1.9-coco-manifests", "formal_protocol_v1.9"),
        _asset("lpips-alex-v0.1", "lpips-0.1.4-v0.1"),
        _asset("alexnet-imagenet1k", "torchvision-0.16.2-IMAGENET1K_V1"),
        _asset("inception-v3-imagenet1k", "torchvision-0.16.2-IMAGENET1K_V1"),
    ]}
    with pytest.raises(ValueError, match="v1.10"):
        validate_formal_assets(payload)


def test_low_rank_fid_matches_standard_covariance_formula():
    rng = np.random.default_rng(205)
    first = rng.normal(size=(8, 5))
    second = rng.normal(size=(8, 5))
    mu1, mu2 = first.mean(0), second.mean(0)
    sigma1, sigma2 = np.cov(first, rowvar=False), np.cov(second, rowvar=False)
    cross = sqrtm(sigma1 @ sigma2)
    expected = float((mu1 - mu2) @ (mu1 - mu2) + np.trace(sigma1 + sigma2 - 2 * cross.real))
    assert _fid(first, second) == pytest.approx(expected, rel=1e-9, abs=1e-9)


def test_fid_is_zero_for_identical_collections():
    values = np.arange(24, dtype=float).reshape(6, 4)
    assert _fid(values, values) == pytest.approx(0.0, abs=1e-9)


def test_e7_noise_records_post_clipping_norms():
    source = np.full((32, 32, 3), 128, dtype=np.uint8)
    attacked = source.copy()
    attacked[:16] = 220
    controlled, parent_l2, control_l2, control_linf = _matched_noise(
        Image.fromarray(source), Image.fromarray(attacked), 205,
    )
    assert controlled.size == (32, 32)
    assert 0 < control_l2 <= parent_l2
    assert 0 < control_linf <= 1


def test_validated_spool_cleanup_is_scoped_and_idempotent(tmp_path):
    first = tmp_path / "evaluation_spool/a.png"
    second = tmp_path / "curve_checkpoint_spool/c/step_0100.png"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    result = _cleanup_validated_spools(tmp_path)
    assert result == {"status": "COMPLETE", "removed_files": 2, "removed_bytes": 11}
    assert not first.exists() and not second.exists()
    assert _cleanup_validated_spools(tmp_path) == result


def test_eta_report_retains_cleaned_spool_peak_and_runtime_metadata(tmp_path):
    manifest = tmp_path / "manifests/attack_outputs.csv"
    manifest.parent.mkdir(parents=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["final_step", "optimization_compute_time"])
        writer.writeheader()
        writer.writerows([
            {"final_step": 150, "optimization_compute_time": 2.0},
            {"final_step": 150, "optimization_compute_time": 4.0},
            {"final_step": 0, "optimization_compute_time": 0.1},
        ])
    logs = tmp_path / "logs"
    logs.mkdir()
    runtime = {
        "gpu_name": "test-gpu", "torch_version": "test-torch",
        "torch_cuda_version": "test-cuda", "python_version": "3.10",
        "gpu_peak_allocated_bytes": 10, "gpu_peak_reserved_bytes": 20,
    }
    for phase in ("prepare", "attack", "evaluate"):
        (logs / f"{phase}_runtime.json").write_text(json.dumps({**runtime, "phase": phase}), encoding="utf-8")
    (logs / "spool_cleanup.json").write_text(
        json.dumps({"removed_bytes": 123}), encoding="utf-8",
    )
    report = _eta_report(
        tmp_path, {"prepare": 1.0, "attack": 10.0, "evaluate": 2.0},
        tmp_path / "runtime_estimate.json",
    )
    assert report["estimated_peak_spool_bytes"] == 12_300
    assert report["hardware_software"]["gpu_name"] == "test-gpu"
    assert report["p90_seconds"] >= report["p50_seconds"]


def test_wrong_key_bank_reuses_one_image_inversion():
    class Adapter:
        inversions = 0
        def invert(self, image):
            self.inversions += 1
            return image * 2
        def detect_inverted(self, inverted, key):
            return inverted + key
    adapter = Adapter()
    result = _detect_key_bank(adapter, 3, {"a": 1, "b": 2, "c": 3})
    assert result == {"a": 7, "b": 8, "c": 9}
    assert adapter.inversions == 1


def test_v117_trajectory_keeps_non_interval_final_step():
    assert frozen_trajectory_steps(150, 100) == [0, 100, 150]


def test_batch_wrong_key_bank_uses_one_batch_inversion():
    class Adapter:
        calls = 0
        def invert_many(self, images):
            self.calls += 1
            return np.asarray(images)[:, None]
        def detect_inverted(self, inverted, key):
            return int(inverted[0, 0]) + key
    adapter = Adapter()
    result = _detect_key_bank_many(adapter, [3, 4], {"a": 1, "b": 2})
    assert result == [{"a": 4, "b": 5}, {"a": 5, "b": 6}]
    assert adapter.calls == 1
