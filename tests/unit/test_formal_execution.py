import numpy as np
import pytest
import csv
import json
from PIL import Image
from scipy.linalg import sqrtm

from latent_space_aggregation_attacks.formal.attack import _cleanup_consumed_reference_images, _matched_noise
from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.evaluation.metrics import perturbation_metrics
from latent_space_aggregation_attacks.formal.evaluate import FINAL_FIELDS, _cleanup_validated_spools, _condition_summary, _fid, _paper_tables
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


def test_v121_omits_rmse_and_asr_confidence_intervals():
    metrics = perturbation_metrics(np.zeros((2, 2, 3)), np.ones((2, 2, 3)))
    assert set(metrics) == {"l2", "linf"}
    assert "rmse" not in FINAL_FIELDS
    rows = [{
        "condition_id": "c", "run_id": "r", "watermark": "tree_ring",
        "model_setting": "same_model_sd14_target_sd14_vae_proxy", "method": "proposed",
        "N": 5, "lambda": 10000.0, "beta": "", "gamma": "", "eligible": True,
        "success": True, "l2": 1.0, "linf": 0.1, "lpips": 0.2, "ssim": 0.9,
        "psnr": 30.0, "attack_compute_time": 1.0,
    }]
    summary = _condition_summary(rows, {"c": 2.0})[0]
    assert summary["success_n"] == 1 and summary["eligible_n"] == 1 and summary["ASR"] == 1.0
    assert "ASR_ci_low" not in summary and "ASR_ci_high" not in summary


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


def test_removal_tables_keep_beta_out_of_main_lambda_and_n_views(tmp_path):
    def row(method, n, lam, beta="", gamma=""):
        return {
            "Watermark": "tree_ring", "Model": "SDv2.0", "Method": method,
            "N": n, "lambda": lam, "beta": beta, "gamma": gamma,
            "ASR": 0.5, "l2": 1.0, "linf": 0.1, "lpips": 0.2,
            "ssim": 0.9, "psnr": 30.0, "FID": 2.0, "attack_compute_time": 1.0,
        }
    summaries = [
        row("jain", 1, lam) for lam in (10000.0, 20000.0, 50000.0)
    ] + [
        row("proposed", 5, lam, 1.5) for lam in (10000.0, 20000.0, 50000.0)
    ] + [
        row("proposed", n, 10000.0, 1.5) for n in (1, 25)
    ] + [
        row("simple_averaging", n, "", gamma=1.0) for n in (1, 5, 25)
    ] + [
        row("proposed", 5, 10000.0, beta) for beta in (1.0, 2.0)
    ]
    _paper_tables(summaries, tmp_path, task="removal")
    assert len(list(csv.DictReader((tmp_path / "removal_method_table.csv").open()))) == 3
    assert len(list(csv.DictReader((tmp_path / "removal_lambda_proposed_table.csv").open()))) == 3
    assert len(list(csv.DictReader((tmp_path / "removal_N_proposed_table.csv").open()))) == 3
    assert len(list(csv.DictReader((tmp_path / "removal_beta_table.csv").open()))) == 3


def test_validated_spool_cleanup_is_scoped_and_idempotent(tmp_path):
    first = tmp_path / "evaluation_spool/a.png"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    result = _cleanup_validated_spools(tmp_path)
    assert result == {"status": "COMPLETE", "removed_files": 1, "removed_bytes": 5}
    assert not first.exists()
    assert _cleanup_validated_spools(tmp_path) == result


def test_reference_images_are_cleaned_only_after_primary_outputs_verify(tmp_path):
    reference = tmp_path / "prepared_inputs/references/model/watermark/key/ref_00.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"reference")
    output = tmp_path / "evaluation_spool/condition/key.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"output")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    with (manifests / "reference_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_path", "image_sha256"])
        writer.writeheader()
        writer.writerow({
            "image_path": reference.relative_to(tmp_path).as_posix(),
            "image_sha256": sha256_file(reference),
        })
    (tmp_path / "preparation_report.json").write_text(
        json.dumps({"selected_reference_count": 1}), encoding="utf-8",
    )
    result = _cleanup_consumed_reference_images(tmp_path, [{
        "condition_id": "condition", "key_id": "key",
        "output_image_path": output.relative_to(tmp_path).as_posix(),
        "output_sha256": sha256_file(output),
    }], 1)
    assert result["status"] == "COMPLETE" and result["removed_files"] == 1
    assert not reference.exists() and not (tmp_path / "prepared_inputs/references").exists()
    assert output.exists()


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
    (logs / "reference_image_cleanup.json").write_text(
        json.dumps({"removed_bytes": 50}), encoding="utf-8",
    )
    report = _eta_report(
        tmp_path, {"prepare": 1.0, "attack": 10.0, "evaluate": 2.0},
        tmp_path / "runtime_estimate.json",
        config={"validated_batching": {
            "attack_batch_size": 1,
            "inversion_batch_size": 1,
            "reference_encode_batch_size": 1,
            "require_equivalence_gate": False,
        }},
    )
    assert report["estimated_peak_spool_bytes"] == 12_300
    assert report["estimated_selected_reference_bytes"] == 5_000
    assert report["hardware_software"]["gpu_name"] == "test-gpu"
    assert report["hardware_software"]["attack_batch_size"] == 1
    assert report["hardware_software"]["inversion_batch_size"] == 1
    assert report["hardware_software"]["reference_encode_batch_size"] == 1
    assert report["p90_seconds"] >= report["p50_seconds"]
    removal = _eta_report(
        tmp_path, {"prepare": 1.0, "attack": 10.0, "evaluate": 2.0},
        tmp_path / "removal_runtime_estimate.json",
        config={"validated_batching": {
            "attack_batch_size": 1,
            "inversion_batch_size": 1,
            "reference_encode_batch_size": 1,
            "require_equivalence_gate": False,
        }},
        task="removal",
    )
    assert removal["formal_stage_counts"]["primary_attack_outputs"] == 21_600
    assert removal["formal_stage_counts"]["e7_control_outputs"] == 15_600
