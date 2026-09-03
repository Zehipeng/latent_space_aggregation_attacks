from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from latent_space_aggregation_attacks import MASTER_SEED, PROTOCOL_VERSION
from .hashing import stable_hash

MODEL_SETTINGS = {
    "same_model_sd14_target_sd14_vae_proxy",
    "cross_model_sd2_target_sd14_vae_proxy",
}
WATERMARKS = {"tree_ring", "ringid", "gaussian_shading"}


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a mapping")
    config = deepcopy(value)
    config["_source_path"] = str(source)
    validate_config(config)
    config["resolved_config_hash"] = stable_hash({k: v for k, v in config.items() if not k.startswith("_")})
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError(f"protocol_version must be {PROTOCOL_VERSION}")
    if int(config.get("master_seed", -1)) != MASTER_SEED:
        raise ValueError(f"master_seed must be {MASTER_SEED}")
    mode = config.get("run_mode")
    if mode not in {"budget_pilot", "budget_confirmation", "removal_diagnostic", "smoke", "formal"}:
        raise ValueError("Invalid run_mode")
    settings = set(config.get("model_settings", []))
    if mode in {"budget_pilot", "budget_confirmation", "removal_diagnostic"}:
        if settings != {"cross_model_sd2_target_sd14_vae_proxy"}:
            raise ValueError("P0 permits only the cross-model setting")
    elif not settings or not settings.issubset(MODEL_SETTINGS):
        raise ValueError("Formal/smoke model settings are invalid")
    if set(config.get("watermarks", [])) != WATERMARKS:
        raise ValueError("All three registered watermarks are required")
    expected_key_counts = {50} if mode in {"budget_pilot", "budget_confirmation"} else ({10} if mode == "removal_diagnostic" else {2, 200})
    if int(config.get("key_count", 0)) not in expected_key_counts:
        raise ValueError("key_count does not match the run mode")
    pilot_like = mode in {"budget_pilot", "budget_confirmation", "removal_diagnostic"}
    expected_n = [5] if pilot_like else [1, 5, 25]
    expected_lambda = [10000.0] if pilot_like else [10000.0, 20000.0, 50000.0]
    expected_beta = [1.5] if mode == "removal_diagnostic" else ([1.0] if mode in {"budget_pilot", "budget_confirmation"} else [1.0, 1.5, 2.0])
    if config.get("N_values") != expected_n:
        raise ValueError(f"N_values must be {expected_n} for {mode}")
    if config.get("lambda_values") != expected_lambda:
        raise ValueError(f"lambda_values must be {expected_lambda} for {mode}")
    if config.get("beta_values") != expected_beta:
        raise ValueError(f"beta_values must be {expected_beta} for {mode}")
    if float(config.get("learning_rate", -1)) != 0.02:
        raise ValueError("learning_rate must be 0.02")
    if int(config.get("resume_every", -1)) != 50:
        raise ValueError("resume_every must be 50")
    if mode in {"formal", "smoke"}:
        if config.get("output_root") != "/root/autodl-tmp/outputs":
            raise ValueError("formal_protocol_v1.20 output_root must be /root/autodl-tmp/outputs")
        budgets = (config.get("T_forgery_formal"), config.get("T_removal_formal"))
        if any(value in {None, "UNFROZEN"} for value in budgets):
            raise ValueError("Task-level formal budgets are not frozen; formal execution is prohibited")
        if tuple(int(value) for value in budgets) != (150, 150):
            raise ValueError("formal_protocol_v1.20 requires both task budgets to equal 150")
        batching = config.get("validated_batching", {})
        if batching != {
            "attack_batch_size": 1,
            "inversion_batch_size": 1,
            "reference_encode_batch_size": 1,
            "require_equivalence_gate": False,
        }:
            raise ValueError("formal_protocol_v1.20 requires scalar attack, inversion and reference encoding")
        if float(config.get("main_beta", -1)) != 1.5:
            raise ValueError("formal removal main_beta must equal 1.5")
        if config.get("online_detection", False) or config.get("early_stop", False):
            raise ValueError("Formal attack must not use online detection or early stopping")
        if config.get("formal_tasks") != ["forgery", "removal"]:
            raise ValueError("Formal configuration must register forgery and removal in order")
        if config.get("visualization_key_ids") != ["key_000", "key_100", "key_199"]:
            raise ValueError("Formal visualization keys are protocol-locked")
        validity = config.get("reference_validity", {})
        if (
            validity.get("selection_policy") != "first_accepted_from_preregistered_candidates"
            or int(validity.get("candidate_limit", 0)) != 64
            or int(validity.get("selected_count", 0)) != 25
            or validity.get("require_all_selected_accepted") is not True
        ):
            raise ValueError("Formal references require the first 25 accepted of 64 candidates")
        _validate_watermark_runtime(config.get("watermark_runtime"))
    if mode == "budget_pilot":
        tasks = config.get("tasks")
        if tasks not in (["forgery"], ["removal"]):
            raise ValueError("Each P0 config must contain exactly one task")
        expected_t_max = 3000 if tasks == ["forgery"] else 15000
        if int(config.get("T_max", 0)) != expected_t_max or int(config.get("detection_every", 0)) != 100:
            raise ValueError(f"{tasks[0]} P0 requires T_max={expected_t_max} and detection_every=100")
        if not config.get("online_detection") or not config.get("early_stop"):
            raise ValueError("P0 online stage requires detection and early stopping")
        if config.get("visualization_key_ids") != []:
            raise ValueError("P0 does not use a visualization-key subset")
        storage = config.get("p0_storage")
        if storage != {
            "persist_reference_images": False,
            "persist_attack_images": True,
            "persist_asr_curve_images": True,
        }:
            raise ValueError("P0 storage policy is not protocol-locked")
        runtime = config.get("watermark_runtime")
        if not isinstance(runtime, dict) or set(runtime) != WATERMARKS:
            raise ValueError("P0 must explicitly lock runtime parameters for all watermarks")
        if float(runtime["tree_ring"].get("p_value_threshold", -1)) != 0.05:
            raise ValueError("Tree-Ring P0 threshold must be p<=0.05")
        if int(runtime["tree_ring"].get("channel", -1)) != 0 or int(runtime["tree_ring"].get("radius", -1)) != 16:
            raise ValueError("Tree-Ring must be locked to channel=0 and radius=16")
        if float(runtime["ringid"].get("p_value_threshold", -1)) != 0.05:
            raise ValueError("RingID P0 threshold must be p<=0.05")
        gaussian = runtime["gaussian_shading"]
        if float(gaussian.get("fpr", -1)) != 1e-6 or float(gaussian.get("bit_accuracy_threshold", -1)) != 0.6484375:
            raise ValueError("Gaussian Shading P0 must use the registered FPR=1e-6 threshold")
        if gaussian.get("cipher") != "chacha20":
            raise ValueError("Gaussian Shading P0 cipher must be explicitly locked")
        validity = config.get("reference_validity")
        if not isinstance(validity, dict):
            raise ValueError("P0 must define the reference validity policy")
        if validity.get("selection_policy") != "first_accepted_from_preregistered_candidates":
            raise ValueError("P0 reference selection policy is not locked")
        if int(validity.get("candidate_limit", 0)) != 64 or validity.get("require_all_selected_accepted") is not True:
            raise ValueError("P0 requires five valid references from 64 preregistered candidates")
    if mode == "removal_diagnostic":
        if config.get("tasks") != ["removal"] or config.get("methods") != ["proposed"]:
            raise ValueError("Removal diagnostic permits only Proposed removal")
        if (
            int(config.get("main_N", 0)) != 5
            or float(config.get("main_lambda", -1)) != 10000.0
            or float(config.get("main_beta", -1)) != 1.5
            or int(config.get("T_max", 0)) != 3000
        ):
            raise ValueError("Removal diagnostic requires N=5, lambda=10000, beta=1.5 and T_max=3000")
        if config.get("online_detection") or config.get("early_stop"):
            raise ValueError("Removal diagnostic must use fixed budget without online detection")
        if config.get("diagnostic_storage") != {
            "persist_reference_images": False,
            "persist_final_images": True,
            "persist_checkpoint_images": False,
        }:
            raise ValueError("Removal diagnostic storage policy is not protocol-locked")
        if config.get("diagnostic_metrics") != [
            "ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "optimization_progress_pct",
        ]:
            raise ValueError("Removal diagnostic metrics are not protocol-locked")
        validity = config.get("reference_validity", {})
        if (
            validity.get("selection_policy") != "first_accepted_from_preregistered_candidates"
            or int(validity.get("candidate_limit", 0)) != 64
            or validity.get("require_all_selected_accepted") is not True
        ):
            raise ValueError("Removal diagnostic reference validity policy is not protocol-locked")


def _validate_watermark_runtime(runtime: Any) -> None:
    if not isinstance(runtime, dict) or set(runtime) != WATERMARKS:
        raise ValueError("All watermark runtime settings must be explicit")
    tree = runtime["tree_ring"]
    if (
        int(tree.get("channel", -1)) != 0
        or int(tree.get("radius", -1)) != 16
        or float(tree.get("p_value_threshold", -1)) != 0.05
    ):
        raise ValueError("Tree-Ring runtime must use channel=0, radius=16 and p<=0.05")
    if float(runtime["ringid"].get("p_value_threshold", -1)) != 0.05:
        raise ValueError("RingID runtime must use p<=0.05")
    gaussian = runtime["gaussian_shading"]
    if (
        gaussian.get("cipher") != "chacha20"
        or float(gaussian.get("fpr", -1)) != 1e-6
        or float(gaussian.get("bit_accuracy_threshold", -1)) != 0.6484375
    ):
        raise ValueError("Gaussian Shading runtime must use ChaCha20 and the FPR=1e-6 threshold")
