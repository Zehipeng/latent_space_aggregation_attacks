import math

from latent_space_aggregation_attacks.analysis.reliability import (
    normalize_row,
    paired_comparison_rows,
    summarize_conditions,
    wilson_interval,
)


def _row(
    *, key: str, method: str, condition: str, success: bool,
    final_score: float, watermark: str = "tree_ring",
) -> dict[str, str]:
    return {
        "protocol_version": "test",
        "run_id": "run",
        "condition_id": condition,
        "watermark": watermark,
        "model_setting": "same_model_sd14_target_sd14_vae_proxy",
        "task": "forgery",
        "method": method,
        "key_id": key,
        "N": "1",
        "lambda": "20000.0",
        "beta": "",
        "gamma": "",
        "eligible": "True",
        "success": str(success),
        "initial_score": "0.8" if watermark != "gaussian_shading" else "0.5",
        "final_score": str(final_score),
        "lpips": "0.1",
        "ssim": "0.9",
        "psnr": "35.0",
        "l2": "1.0",
        "linf": "0.1",
        "attack_compute_time": "10.0",
    }


def test_wilson_interval_contains_observed_rate() -> None:
    low, high = wilson_interval(80, 100)
    assert 0 <= low < 0.8 < high <= 1
    empty = wilson_interval(0, 0)
    assert all(math.isnan(value) for value in empty)
    assert wilson_interval(0, 200)[0] == 0.0
    assert wilson_interval(200, 200)[1] == 1.0


def test_normalize_detector_margin_directions() -> None:
    tree = normalize_row(
        _row(key="key_000", method="proposed", condition="tree", success=True,
             final_score=0.01),
        "source",
    )
    assert math.isclose(tree["final_acceptance_margin"], 0.04)
    assert math.isclose(tree["final_task_margin"], 0.04)
    gaussian = normalize_row(
        _row(key="key_000", method="proposed", condition="gs", success=True,
             final_score=0.75, watermark="gaussian_shading"),
        "source",
    )
    assert gaussian["final_acceptance_margin"] > 0


def test_condition_summary_and_paired_bootstrap() -> None:
    rows = []
    for index, success in enumerate((True, False, True, True)):
        key = f"key_{index:03d}"
        rows.append(normalize_row(
            _row(key=key, method="proposed", condition="proposed", success=success,
                 final_score=0.01 if success else 0.2),
            "source",
        ))
        rows.append(normalize_row(
            _row(key=key, method="matched_gaussian_noise",
                 condition="e7_matched_noise_of__proposed", success=False,
                 final_score=0.3),
            "source",
        ))
    summary = summarize_conditions(rows, bootstrap_replicates=50)
    proposed = next(row for row in summary if row["condition_id"] == "proposed")
    assert proposed["eligible_n"] == 4
    assert proposed["success_n"] == 3
    assert proposed["ASR"] == 0.75
    paired = paired_comparison_rows(rows, bootstrap_replicates=50)
    success = next(row for row in paired if row["metric"] == "success")
    assert success["paired_n"] == 4
    assert success["mean_paired_difference_left_minus_right"] == 0.75
