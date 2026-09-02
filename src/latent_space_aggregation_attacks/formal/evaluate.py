from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.evaluation.eligibility import success as attack_success
from latent_space_aggregation_attacks.evaluation.metrics import paired_quality_metrics, wrong_identity_metrics
from latent_space_aggregation_attacks.evaluation.statistics import (
    bootstrap_ci, holm_adjust, mcnemar_exact, paired_wilcoxon, wilson_interval,
)
from latent_space_aggregation_attacks.models.loaders import load_target_pipeline
from latent_space_aggregation_attacks.plotting.trajectories import plot_detector_trajectory
from latent_space_aggregation_attacks.watermarks.base import registered_adapter

from ..core.atomic_io import atomic_write_json, atomic_write_text
from .common import (
    adapter_config, assets_by_name, atomic_csv, canonical_512, formal_inputs, frozen_trajectory_steps, model_config,
    open_rgb, read_csv, threshold,
)
from ..core.hashing import sha256_file, stable_hash
from ..core.ledger import LedgerEvent, append_event
from ..core.seeds import configure_torch_determinism, derive_seed

FINAL_FIELDS = [
    "protocol_version", "run_id", "condition_id", "watermark", "model_setting",
    "task", "method", "key_id", "target_id", "reference_ids", "clean_ids",
    "N", "lambda", "beta", "gamma", "seed", "final_step", "eligible",
    "success", "initial_score", "final_score", "score_name", "accepted_after",
    "wrong_key_checked", "wrong_key_accept_count", "any_wrong_key_accept",
    "target_rank", "target_top1", "l2", "linf", "rmse", "lpips", "ssim",
    "psnr", "attack_compute_time", "output_sha256", "output_image_path",
]
TRAJECTORY_FIELDS = [
    "protocol_version", "run_id", "condition_id", "task", "watermark",
    "model_setting", "model", "key_id", "factor_name", "factor_value", "step",
    "score_name", "score", "threshold",
]
TRAJECTORY_SUMMARY_FIELDS = [
    "protocol_version", "run_id", "task", "watermark", "model_setting", "model",
    "factor_name", "factor_value", "step", "n", "center", "lower", "upper",
    "score_name", "threshold",
]


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _report_artifacts_are_valid(root: Path, report: dict[str, Any]) -> bool:
    hashes = report.get("hashes", {})
    return bool(hashes) and all(
        (root / relative).is_file() and sha256_file(root / relative) == digest
        for relative, digest in hashes.items()
    )


def _write_evaluation_progress(
    root: Path, *, completed: int, total: int, durations: list[float], stage: str = "evaluation",
) -> None:
    window = sorted(durations[-100:])
    rolling = window[len(window) // 2] if window else 0.0
    remaining = max(0, total - completed)
    now = datetime.now(timezone.utc)
    atomic_write_json(root / "progress.json", {
        "stage": stage, "completed_units": completed, "total_units": total,
        "remaining_units": remaining, "rolling_median_seconds_per_unit": rolling,
        "estimated_remaining_seconds": rolling * remaining,
        "estimated_completion_utc": (now + timedelta(seconds=rolling * remaining)).isoformat(),
        "updated_at_utc": now.isoformat(),
    })


def _cleanup_validated_spools(root: Path) -> dict[str, int | str]:
    import json
    inventory_path = root / "logs/spool_cleanup_inventory.json"
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    else:
        inventory = [
            {"path": path.relative_to(root).as_posix(), "size": path.stat().st_size}
            for relative in ("evaluation_spool", "curve_checkpoint_spool")
            for path in sorted((root / relative).rglob("*"))
            if path.is_file()
        ]
        atomic_write_json(inventory_path, inventory)
    allowed_roots = tuple((root / name).resolve() for name in ("evaluation_spool", "curve_checkpoint_spool"))
    for item in inventory:
        path = (root / item["path"]).resolve()
        if not any(path.is_relative_to(allowed) for allowed in allowed_roots):
            raise RuntimeError(f"Unsafe spool cleanup inventory path: {path}")
        path.unlink(missing_ok=True)
    for relative in ("evaluation_spool", "curve_checkpoint_spool"):
        spool = root / relative
        if not spool.exists():
            continue
        for directory in sorted(
            (path for path in spool.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts), reverse=True,
        ):
            directory.rmdir()
        spool.rmdir()
    detail = {
        "status": "COMPLETE", "removed_files": len(inventory),
        "removed_bytes": sum(int(item["size"]) for item in inventory),
    }
    append_event(
        root / "logs/unit_ledger.jsonl",
        LedgerEvent("__validated_spool_cleanup__", "COMPLETE", str(detail)),
    )
    atomic_write_json(root / "logs/spool_cleanup.json", detail)
    return detail


def _lpips_model(assets: dict[str, dict[str, Any]]) -> Any:
    import lpips
    import torch
    torch.hub.set_dir(str(Path(assets["alexnet-imagenet1k"]["path"]).resolve().parents[1]))
    return lpips.LPIPS(net="alex", version="0.1", verbose=False).to("cuda").eval()


def _model_label(setting: str) -> str:
    return "SDv1.4" if setting.startswith("same_model") else "SDv2.0"


def _key_bank(adapter: Any, watermark: str, key_ids: list[str]) -> dict[str, Any]:
    return {
        key_id: adapter.create_key({
            "key_id": key_id,
            "watermark_seed": derive_seed("watermark_key", watermark, key_id),
        })
        for key_id in key_ids
    }


def _detect_key_bank(adapter: Any, image: Any, keys: dict[str, Any]) -> dict[str, Any]:
    """Invert an image once, then score every registered identity."""
    inverted = adapter.invert(image)
    return {key_id: adapter.detect_inverted(inverted, key) for key_id, key in keys.items()}


def _detect_key_bank_many(adapter: Any, images: list[Any], keys: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch-invert independent images, then score each against the full key bank."""
    inverted = adapter.invert_many(images)
    return [
        {key_id: adapter.detect_inverted(inverted[index:index + 1], key) for key_id, key in keys.items()}
        for index in range(len(images))
    ]


def _trajectory_factor(row: dict[str, str]) -> list[tuple[str, str]]:
    if row["method"] != "proposed":
        return []
    values: list[tuple[str, str]] = []
    if int(float(row["N"])) == 5 and float(row["lambda"]) in {10000.0, 20000.0, 50000.0}:
        values.append(("lambda", str(float(row["lambda"]))))
    if float(row["lambda"]) == 10000.0 and int(float(row["N"])) in {1, 5, 25}:
        values.append(("N", str(int(float(row["N"])))))
    return values


def _summarize_trajectories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[float]] = defaultdict(list)
    metadata: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["watermark"], row["model_setting"], row["model"], row["factor_name"],
            str(row["factor_value"]), str(row["step"]), row["score_name"], str(row["threshold"]),
        )
        grouped[key].append(float(row["score"]))
        metadata[key] = row
    result = []
    for key, values in sorted(grouped.items()):
        row = metadata[key]
        array = np.asarray(values, dtype=float)
        if row["watermark"] == "gaussian_shading":
            center = float(array.mean())
            low, high = bootstrap_ci(array, seed=derive_seed("worker", "trajectory", *key), samples=2000)
        else:
            center = float(np.median(array))
            low, high = map(float, np.quantile(array, [0.25, 0.75]))
        result.append({
            "protocol_version": PROTOCOL_VERSION, "run_id": row["run_id"],
            "task": "forgery", "watermark": row["watermark"],
            "model_setting": row["model_setting"], "model": row["model"],
            "factor_name": row["factor_name"], "factor_value": row["factor_value"],
            "step": int(row["step"]), "n": len(values), "center": center,
            "lower": low, "upper": high, "score_name": row["score_name"],
            "threshold": row["threshold"],
        })
    return result


def _condition_summary(rows: list[dict[str, Any]], fid_by_condition: dict[str, float]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition_id"]].append(row)
    summaries = []
    for condition_id, group in sorted(grouped.items()):
        eligible = [row for row in group if _as_bool(row["eligible"])]
        successes = sum(_as_bool(row["success"]) for row in eligible)
        low, high = wilson_interval(successes, len(eligible)) if eligible else (float("nan"), float("nan"))
        first = group[0]
        summaries.append({
            "protocol_version": PROTOCOL_VERSION, "run_id": first["run_id"],
            "condition_id": condition_id, "Watermark": first["watermark"],
            "Model": _model_label(first["model_setting"]), "Method": first["method"],
            "N": first["N"], "lambda": first["lambda"], "beta": first["beta"],
            "gamma": first["gamma"], "sample_n": len(group), "eligible_n": len(eligible),
            "success_n": successes, "ASR": successes / len(eligible) if eligible else "",
            "ASR_ci_low": low if eligible else "", "ASR_ci_high": high if eligible else "",
            **{
                metric: float(np.mean([float(row[metric]) for row in group]))
                for metric in ("l2", "linf", "lpips", "ssim", "psnr", "attack_compute_time")
            },
            "FID": fid_by_condition[condition_id],
        })
    return summaries


def _inception_model(weight_path: str | Path) -> Any:
    import torch
    from torchvision.models import inception_v3
    model = inception_v3(weights=None, aux_logits=True, transform_input=False)
    payload = torch.load(weight_path, map_location="cpu")
    model.load_state_dict(payload)
    model.fc = torch.nn.Identity()
    return model.to("cuda").eval()


def _activations(model: Any, paths: list[str | Path], batch_size: int = 16) -> np.ndarray:
    import torch
    import torch.nn.functional as functional
    tensors = []
    output = []
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)
    for path in paths:
        array = np.asarray(canonical_512(open_rgb(path)), dtype=np.float32) / 255.0
        tensors.append(torch.from_numpy(array).permute(2, 0, 1))
        if len(tensors) == batch_size:
            batch = functional.interpolate(torch.stack(tensors).to("cuda"), size=(299, 299), mode="bilinear", align_corners=False)
            with torch.inference_mode():
                output.append(model((batch - mean) / std).float().cpu().numpy())
            tensors = []
    if tensors:
        batch = functional.interpolate(torch.stack(tensors).to("cuda"), size=(299, 299), mode="bilinear", align_corners=False)
        with torch.inference_mode():
            output.append(model((batch - mean) / std).float().cpu().numpy())
    return np.concatenate(output, axis=0)


def _fid(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape or first.shape[0] < 2:
        raise ValueError("FID requires two equal collections with at least two images")
    mu1, mu2 = first.mean(0), second.mean(0)
    centered_first = (first - mu1) / math.sqrt(first.shape[0] - 1)
    centered_second = (second - mu2) / math.sqrt(second.shape[0] - 1)
    # The covariance matrices are 2048x2048 but have rank at most n-1.
    # The nuclear norm of A @ B.T yields the exact covariance cross term
    # while reducing the SVD to at most 200x200 for the formal collections.
    cross_trace = np.linalg.svd(centered_first @ centered_second.T, compute_uv=False).sum()
    value = (
        (mu1 - mu2) @ (mu1 - mu2)
        + np.square(centered_first).sum() + np.square(centered_second).sum()
        - 2.0 * cross_trace
    )
    return float(max(value, 0.0))


def _paper_tables(summaries: list[dict[str, Any]], output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    metric_columns = ["ASR", "l2", "linf", "LPIPS", "SSIM", "PSNR", "FID", "Time"]
    def table_row(row: dict[str, Any], variable: str, value: Any) -> dict[str, Any]:
        return {
            "Watermark": row["Watermark"], "Model": row["Model"], variable: value,
            "ASR": row["ASR"], "l2": row["l2"], "linf": row["linf"],
            "LPIPS": row["lpips"], "SSIM": row["ssim"], "PSNR": row["psnr"],
            "FID": row["FID"], "Time": row["attack_compute_time"],
        }
    outputs: list[Path] = []
    main = [
        row for row in summaries
        if (
            (row["Method"] == "jain" and float(row["lambda"]) == 10000.0)
            or (row["Method"] == "simple_averaging" and int(row["N"]) == 5)
            or (row["Method"] == "proposed" and int(row["N"]) == 5 and float(row["lambda"]) == 10000.0)
        )
    ]
    path = output / "forgery_method_table.csv"
    atomic_csv(path, [table_row(row, "Method", row["Method"]) for row in main], ["Watermark", "Model", "Method", *metric_columns])
    outputs.append(path)
    for method in ("jain", "proposed"):
        selected = [row for row in summaries if row["Method"] == method and int(row["N"]) == (1 if method == "jain" else 5)]
        path = output / f"forgery_lambda_{method}_table.csv"
        atomic_csv(path, [table_row(row, "lambda", row["lambda"]) for row in selected], ["Watermark", "Model", "lambda", *metric_columns])
        outputs.append(path)
    for method in ("proposed", "simple_averaging"):
        selected = [
            row for row in summaries
            if row["Method"] == method and (method == "simple_averaging" or float(row["lambda"]) == 10000.0)
        ]
        path = output / f"forgery_N_{method}_table.csv"
        atomic_csv(path, [table_row(row, "N", row["N"]) for row in selected], ["Watermark", "Model", "N", *metric_columns])
        outputs.append(path)
    return outputs


def _main_statistics(rows: list[dict[str, Any]], output: Path) -> Path:
    results = []
    for watermark in ("tree_ring", "ringid", "gaussian_shading"):
        for model_setting in ("same_model_sd14_target_sd14_vae_proxy", "cross_model_sd2_target_sd14_vae_proxy"):
            panel = [row for row in rows if row["watermark"] == watermark and row["model_setting"] == model_setting]
            jain = {
                row["key_id"]: row for row in panel
                if row["method"] == "jain" and int(float(row["N"])) == 1 and float(row["lambda"]) == 10000.0
            }
            proposed = {
                row["key_id"]: row for row in panel
                if row["method"] == "proposed" and int(float(row["N"])) == 5 and float(row["lambda"]) == 10000.0
            }
            keys = sorted(set(jain) & set(proposed))
            eligible = [key for key in keys if _as_bool(jain[key]["eligible"]) and _as_bool(proposed[key]["eligible"])]
            mcnemar = mcnemar_exact(
                [_as_bool(jain[key]["success"]) for key in eligible],
                [_as_bool(proposed[key]["success"]) for key in eligible],
            )
            for metric in ("success", "l2", "lpips"):
                if metric == "success":
                    results.append({
                        "family": "main_forgery", "watermark": watermark,
                        "model_setting": model_setting, "comparison": "proposed_vs_jain",
                        "metric": metric, "n": len(eligible), "effect": mcnemar["second_only"] - mcnemar["first_only"],
                        "p_value": mcnemar["p_value"],
                    })
                else:
                    paired = paired_wilcoxon(
                        [float(jain[key][metric]) for key in keys],
                        [float(proposed[key][metric]) for key in keys],
                    )
                    results.append({
                        "family": "main_forgery", "watermark": watermark,
                        "model_setting": model_setting, "comparison": "proposed_vs_jain",
                        "metric": metric, "n": len(keys), "effect": paired["median_paired_difference"],
                        "p_value": paired["p_value"],
                    })
    adjusted = holm_adjust([float(row["p_value"]) for row in results])
    for row, value in zip(results, adjusted):
        row["holm_p_value"] = value
    atomic_csv(output, results)
    return output


def _diagnostic_tables(
    rows: list[dict[str, Any]], summaries: list[dict[str, Any]], output: Path, *, budget: int,
) -> list[Path]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition_id"]].append(row)
    wrong_key_rows = []
    for condition_id, group in sorted(grouped.items()):
        first = group[0]
        wrong_key_rows.append({
            "condition_id": condition_id, "Watermark": first["watermark"],
            "Model": _model_label(first["model_setting"]), "Method": first["method"],
            "sample_n": len(group),
            "any_wrong_key_accept_rate": float(np.mean([_as_bool(row["any_wrong_key_accept"]) for row in group])),
            "mean_wrong_key_accept_count": float(np.mean([int(row["wrong_key_accept_count"]) for row in group])),
            "target_top1_rate": float(np.mean([_as_bool(row["target_top1"]) for row in group])),
            "mean_target_rank": float(np.mean([int(row["target_rank"]) for row in group])),
        })
    wrong_path = output / "wrong_key_diagnostics.csv"
    atomic_csv(wrong_path, wrong_key_rows)
    failures = [
        row for row in rows
        if row["method"] != "matched_gaussian_noise" and _as_bool(row["eligible"]) and not _as_bool(row["success"])
    ]
    failure_path = output / "failed_samples.csv"
    atomic_csv(failure_path, failures, FINAL_FIELDS)
    ineligible = [
        row for row in rows
        if row["method"] != "matched_gaussian_noise" and not _as_bool(row["eligible"])
    ]
    ineligible_path = output / "ineligible_samples.csv"
    atomic_csv(ineligible_path, ineligible, FINAL_FIELDS)
    main = [
        row for row in summaries
        if (
            (row["Method"] == "jain" and float(row["lambda"]) == 10000.0)
            or (row["Method"] == "simple_averaging" and int(row["N"]) == 5)
            or (row["Method"] == "proposed" and int(row["N"]) == 5 and float(row["lambda"]) == 10000.0)
        )
    ]
    costs = []
    for row in main:
        iterative = row["Method"] in {"jain", "proposed"}
        costs.append({
            "Watermark": row["Watermark"], "Model": row["Model"], "Method": row["Method"],
            "ReferenceCount": row["N"], "ProxyVAERequired": iterative,
            "OptimizationSteps": budget if iterative else 0,
            "ApproximateOptimizationVAECalls": budget if iterative else 0,
            "MeanAttackTimeSeconds": row["attack_compute_time"],
            "OnlineDetectorQueries": 0, "EarlyStopping": False,
        })
    cost_path = output / "cost_and_permissions.csv"
    atomic_csv(cost_path, costs)
    return [wrong_path, failure_path, ineligible_path, cost_path]


def _condition_fids(
    *, rows: list[dict[str, Any]], root: Path, target_by_key: dict[str, dict[str, str]],
    assets: dict[str, dict[str, Any]], key_ids: list[str],
) -> dict[str, float]:
    import torch
    model = _inception_model(assets["inception-v3-imagenet1k"]["path"])
    source_features = _activations(model, [target_by_key[key_id]["path"] for key_id in key_ids])
    fid_unit_dir = root / "evaluation/fid_units"
    fid_unit_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition_id"]].append(row)
    result = {}
    durations: list[float] = []
    for index, (condition_id, group) in enumerate(sorted(grouped.items()), 1):
        unit_started = time.perf_counter()
        by_key = {row["key_id"]: row for row in group}
        if set(by_key) != set(key_ids):
            raise RuntimeError(f"FID collection is incomplete: {condition_id}")
        collection_hash = stable_hash([by_key[key_id]["output_sha256"] for key_id in key_ids])
        record_path = fid_unit_dir / f"{stable_hash(condition_id)}.json"
        if record_path.is_file():
            import json
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("condition_id") == condition_id and record.get("collection_hash") == collection_hash:
                result[condition_id] = float(record["FID"])
                durations.append(time.perf_counter() - unit_started)
                _write_evaluation_progress(
                    root, completed=index, total=len(grouped), durations=durations,
                    stage="fid_and_reporting",
                )
                continue
        attacked = _activations(model, [root / by_key[key_id]["output_image_path"] for key_id in key_ids])
        result[condition_id] = _fid(source_features, attacked)
        atomic_write_json(record_path, {
            "condition_id": condition_id, "collection_hash": collection_hash,
            "sample_n": len(key_ids), "FID": result[condition_id],
        })
        durations.append(time.perf_counter() - unit_started)
        _write_evaluation_progress(
            root, completed=index, total=len(grouped), durations=durations,
            stage="fid_and_reporting",
        )
    del model
    torch.cuda.empty_cache()
    return result


def evaluate_formal_forgery(
    *, config: dict[str, Any], assets_lock: dict[str, Any], run_dir: str | Path,
    run_id: str, key_ids: list[str], smoke: bool,
) -> dict[str, Any]:
    """Run detector and quality evaluation in a process separate from attack execution."""
    root = Path(run_dir)
    report_path = root / ("smoke_report.json" if smoke else "evaluation_report.json")
    if report_path.is_file():
        import json
        prior_report = json.loads(report_path.read_text(encoding="utf-8"))
        if _report_artifacts_are_valid(root, prior_report):
            if prior_report.get("spool_cleanup_status") != "COMPLETE":
                prior_report["spool_cleanup"] = _cleanup_validated_spools(root)
                prior_report["spool_cleanup_status"] = "COMPLETE"
                atomic_write_json(report_path, prior_report)
            _write_evaluation_progress(
                root, completed=int(prior_report["final_row_count"]),
                total=int(prior_report["final_row_count"]), durations=[], stage="complete",
            )
            return prior_report
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Formal evaluation requires a CUDA GPU")
    configure_torch_determinism(torch)
    if not (root / "attack_report.json").is_file():
        raise RuntimeError("Attack must complete before independent evaluation")
    assets = assets_by_name(assets_lock)
    _, target_by_key, _ = formal_inputs(assets)
    attack_rows = read_csv(root / "manifests/attack_outputs.csv")
    lpips_model = _lpips_model(assets)
    import json
    final_path = root / "evaluation/final_per_key_metrics.csv"
    trajectory_path = root / "evaluation/detector_trajectory_per_key.csv"
    final_unit_dir = root / "evaluation/final_units"
    trajectory_unit_dir = root / "evaluation/trajectory_units"
    final_unit_dir.mkdir(parents=True, exist_ok=True)
    trajectory_unit_dir.mkdir(parents=True, exist_ok=True)
    final_rows: list[dict[str, Any]] = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(final_unit_dir.glob("*.json"))
    ]
    attack_index = {(row["condition_id"], row["key_id"]): row for row in attack_rows}
    final_rows = [
        row for row in final_rows
        if (row["condition_id"], row["key_id"]) in attack_index
        and row.get("output_sha256") == attack_index[(row["condition_id"], row["key_id"])]["output_sha256"]
        and (root / row["output_image_path"]).is_file()
        and sha256_file(root / row["output_image_path"]) == row["output_sha256"]
    ]
    trajectory_rows: list[dict[str, Any]] = [
        row for path in sorted(trajectory_unit_dir.glob("*.json"))
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]
    completed_final = {(row["condition_id"], row["key_id"]) for row in final_rows}
    completed_trajectory = {
        (row["condition_id"], row["key_id"], row["factor_name"], str(row["factor_value"]), int(row["step"]))
        for row in trajectory_rows
    }
    evaluation_durations: list[float] = []
    visited_outputs = 0
    final_inversion_images = 0
    trajectory_unique_inversions = 0
    atomic_write_text(root / "logs/evaluation_command.txt", " ".join(__import__("sys").argv) + "\n")
    for model_setting in config["model_settings"]:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in config["watermarks"]:
            adapter = registered_adapter(watermark, adapter_config(config, watermark, pipe, assets))
            keys = _key_bank(adapter, watermark, key_ids)
            cutoff = threshold(config, watermark)
            selected = [
                row for row in attack_rows
                if row["model_setting"] == model_setting and row["watermark"] == watermark
            ]
            initial_cache: dict[str, Any] = {}
            inversion_batch_size = int(config["validated_batching"]["inversion_batch_size"])
            source_key_ids = sorted({
                row["key_id"] for row in selected
                if (row["condition_id"], row["key_id"]) not in completed_final
            })
            for offset in range(0, len(source_key_ids), inversion_batch_size):
                batch_keys = source_key_ids[offset:offset + inversion_batch_size]
                sources = [canonical_512(open_rgb(target_by_key[key_id]["path"])) for key_id in batch_keys]
                inverted = adapter.invert_many(sources)
                for index, key_id in enumerate(batch_keys):
                    initial_cache[key_id] = adapter.detect_inverted(inverted[index:index + 1], keys[key_id])
            final_detection_cache: dict[tuple[str, str], dict[str, Any]] = {}
            pending_final = [
                row for row in selected
                if (row["condition_id"], row["key_id"]) not in completed_final
            ]
            for offset in range(0, len(pending_final), inversion_batch_size):
                batch_rows = pending_final[offset:offset + inversion_batch_size]
                images = [open_rgb(root / row["output_image_path"]) for row in batch_rows]
                detections = _detect_key_bank_many(adapter, images, keys)
                final_inversion_images += len(batch_rows)
                for row, value in zip(batch_rows, detections):
                    final_detection_cache[(row["condition_id"], row["key_id"])] = value
            trajectory_detection_cache: dict[tuple[str, str, int], Any] = {}
            trajectory_work: list[tuple[dict[str, str], int, Path]] = []
            for row in selected:
                factors = _trajectory_factor(row)
                if not factors:
                    continue
                for step in frozen_trajectory_steps(
                    int(config["T_forgery_formal"]), int(config["trajectory_every"])
                ):
                    missing = [
                        (factor_name, factor_value) for factor_name, factor_value in factors
                        if (row["condition_id"], row["key_id"], factor_name, factor_value, step)
                        not in completed_trajectory
                    ]
                    if missing:
                        checkpoint = root / "curve_checkpoint_spool" / row["condition_id"] / row["key_id"] / f"step_{step:04d}.png"
                        if not checkpoint.is_file():
                            raise FileNotFoundError(checkpoint)
                        trajectory_work.append((row, step, checkpoint))
            for offset in range(0, len(trajectory_work), inversion_batch_size):
                work = trajectory_work[offset:offset + inversion_batch_size]
                inverted = adapter.invert_many([open_rgb(path) for _, _, path in work])
                trajectory_unique_inversions += len(work)
                for index, (row, step, _) in enumerate(work):
                    trajectory_detection_cache[(row["condition_id"], row["key_id"], step)] = adapter.detect_inverted(
                        inverted[index:index + 1], keys[row["key_id"]]
                    )
            for row in selected:
                evaluation_unit_started = time.perf_counter()
                key_id = row["key_id"]
                source = canonical_512(open_rgb(target_by_key[key_id]["path"]))
                attacked = open_rgb(root / row["output_image_path"])
                if (row["condition_id"], key_id) not in completed_final:
                    initial = initial_cache[key_id]
                    detections = final_detection_cache[(row["condition_id"], key_id)]
                    final = detections[key_id]
                    scores = {other: detection.score for other, detection in detections.items()}
                    wrong = wrong_identity_metrics(
                        key_id, scores, cutoff, lower_is_accept=watermark != "gaussian_shading",
                    )
                    eligible, succeeded, accepted_after = attack_success(
                        "forgery", watermark, initial.score, final.score, cutoff,
                    )
                    quality = paired_quality_metrics(source, attacked, lpips_model)
                    diff = np.asarray(attacked, dtype=np.float32) / 255.0 - np.asarray(source, dtype=np.float32) / 255.0
                    final_rows.append({
                        **{field: row.get(field, "") for field in ATTACK_COPY_FIELDS},
                        "eligible": eligible, "success": succeeded,
                        "initial_score": initial.score, "final_score": final.score,
                        "score_name": final.score_name, "accepted_after": accepted_after,
                        **wrong, "l2": quality["l2"], "linf": quality["linf"],
                        "rmse": float(np.sqrt(np.mean(diff ** 2))), "lpips": quality["LPIPS"],
                        "ssim": quality["SSIM"], "psnr": quality["PSNR"],
                        "attack_compute_time": float(row["optimization_compute_time"]),
                    })
                    completed_final.add((row["condition_id"], key_id))
                    atomic_write_json(
                        final_unit_dir / f"{stable_hash(row['condition_id'] + '|' + key_id)}.json",
                        final_rows[-1],
                    )
                unit_trajectory_rows: list[dict[str, Any]] = []
                factors = _trajectory_factor(row)
                for step in frozen_trajectory_steps(
                    int(config["T_forgery_formal"]), int(config["trajectory_every"])
                ) if factors else []:
                    detected = trajectory_detection_cache.get((row["condition_id"], key_id, step))
                    for factor_name, factor_value in factors:
                        trajectory_identity = (row["condition_id"], key_id, factor_name, factor_value, step)
                        if trajectory_identity in completed_trajectory:
                            continue
                        if detected is None:
                            raise RuntimeError(f"Missing deduplicated trajectory detection: {row['condition_id']}|{key_id}|{step}")
                        trajectory_record = {
                            "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
                            "condition_id": row["condition_id"], "task": "forgery",
                            "watermark": watermark, "model_setting": model_setting,
                            "model": _model_label(model_setting), "key_id": key_id,
                            "factor_name": factor_name, "factor_value": factor_value,
                            "step": step, "score_name": detected.score_name,
                            "score": detected.score, "threshold": cutoff,
                        }
                        trajectory_rows.append(trajectory_record)
                        unit_trajectory_rows.append(trajectory_record)
                        completed_trajectory.add(trajectory_identity)
                if unit_trajectory_rows:
                    atomic_write_json(
                        trajectory_unit_dir / f"{stable_hash(row['condition_id'] + '|' + key_id)}.json",
                        [
                            value for value in trajectory_rows
                            if value["condition_id"] == row["condition_id"] and value["key_id"] == key_id
                        ],
                    )
                visited_outputs += 1
                evaluation_durations.append(time.perf_counter() - evaluation_unit_started)
                _write_evaluation_progress(
                    root, completed=visited_outputs, total=len(attack_rows),
                    durations=evaluation_durations,
                )
            del keys, adapter
        del pipe
        torch.cuda.empty_cache()
    expected = len(attack_rows)
    if len(final_rows) != expected:
        raise RuntimeError(f"Final evaluation produced {len(final_rows)} rows; expected {expected}")
    if len({(row["condition_id"], row["key_id"]) for row in final_rows}) != expected:
        raise RuntimeError("Final evaluation contains duplicate or missing condition/key rows")
    steps_per_unit = len(frozen_trajectory_steps(
        int(config["T_forgery_formal"]), int(config["trajectory_every"])
    ))
    expected_trajectory = (
        len(config["model_settings"]) * len(config["watermarks"]) * 6
        * len(key_ids) * steps_per_unit
    )
    if len(completed_trajectory) != expected_trajectory or len(trajectory_rows) != expected_trajectory:
        raise RuntimeError(
            f"Trajectory evaluation produced {len(trajectory_rows)} rows; expected {expected_trajectory}"
        )
    atomic_csv(final_path, final_rows, FINAL_FIELDS)
    del lpips_model
    torch.cuda.empty_cache()
    fid_by_condition = _condition_fids(
        rows=final_rows, root=root, target_by_key=target_by_key, assets=assets, key_ids=key_ids,
    )
    summaries = _condition_summary(final_rows, fid_by_condition)
    atomic_csv(root / "evaluation/final_condition_summary.csv", summaries)
    table_paths = _paper_tables(summaries, root / "evaluation/tables")
    statistics_path = _main_statistics(final_rows, root / "evaluation/statistical_tests.csv")
    diagnostic_paths = _diagnostic_tables(
        final_rows, summaries, root / "evaluation", budget=int(config["T_forgery_formal"])
    )
    trajectory_summary = _summarize_trajectories(trajectory_rows)
    atomic_csv(trajectory_path, trajectory_rows, TRAJECTORY_FIELDS)
    atomic_csv(root / "evaluation/detector_trajectory_summary.csv", trajectory_summary, TRAJECTORY_SUMMARY_FIELDS)
    thresholds = {watermark: threshold(config, watermark) for watermark in config["watermarks"]}
    figures = [
        plot_detector_trajectory(trajectory_summary, "forgery", factor, root / "figures", thresholds)
        for factor in ("lambda", "N")
    ]
    status = "PASSED" if smoke else "COMPLETE"
    if not smoke:
        import datetime
        import json
        run_manifest = json.loads((root / "manifests/run_manifest.json").read_text(encoding="utf-8"))
        eligible_n = sum(_as_bool(row["eligible"]) for row in final_rows if row["method"] != "matched_gaussian_noise")
        success_n = sum(
            _as_bool(row["success"]) for row in final_rows
            if row["method"] != "matched_gaussian_noise" and _as_bool(row["eligible"])
        )
        failed_n = eligible_n - success_n
        atomic_write_text(root / f"{run_id}_实验总结.md", (
            f"# 正式伪造实验总结\n\n"
            f"- 实验状态：{status}\n- 协议版本：{PROTOCOL_VERSION}\n- run_id：`{run_id}`\n"
            f"- 分析日期：{datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
            f"- 结果来源：`evaluation/final_per_key_metrics.csv`、`evaluation/final_condition_summary.csv`\n"
            f"- 完整Git SHA：`{run_manifest['git_sha']}`\n"
            f"- resolved-config哈希：`{run_manifest['source_resolved_config_hash']}`\n"
            f"- 资产锁哈希：`{run_manifest['assets_lock_hash']}`\n"
            f"- 样本manifest哈希：`{run_manifest['sample_manifest_hash']}`\n"
            f"- 样本量：{len(key_ids)} keys；最终逐key行数：{len(final_rows)}；轨迹逐key行数：{len(trajectory_rows)}\n"
            f"- 非E7资格行：{eligible_n}；成功行：{success_n}；失败行：{failed_n}\n"
            f"- 完整性检查：持久结果文件写入`checksums.sha256`后才清理临时spool\n"
            f"- 异常：无未处理异常\n\n"
            "## 结论边界\n\n"
            f"本文件只确认{PROTOCOL_VERSION}伪造批次计算与完整性链完成。"
            "各水印、模型和方法的正式数值及统计不确定性必须从上述CSV、统计附表和固定表格读取；"
            "不得把历史P0、移除诊断或E7随机噪声控制计入主方法ASR排名。\n"
        ))
    persistent_paths = [
        root / "preparation_report.json",
        root / "attack_report.json",
        root / "manifests/run_manifest.json",
        root / "manifests/reference_candidate_manifest.csv",
        root / "manifests/reference_selection_control.csv",
        root / "manifests/reference_manifest.csv",
        root / "evaluation/e0_original_detection.csv",
        root / "manifests/attack_outputs.csv",
        root / "protocol_snapshot/source_config.yaml",
        root / "protocol_snapshot/config_resolved.json",
        root / f"protocol_snapshot/{PROTOCOL_VERSION}.md",
        root / "evaluation/final_per_key_metrics.csv",
        root / "evaluation/final_condition_summary.csv",
        root / "evaluation/detector_trajectory_per_key.csv",
        root / "evaluation/detector_trajectory_summary.csv",
        *figures, *table_paths, statistics_path, *diagnostic_paths,
    ]
    if not smoke:
        persistent_paths.append(root / f"{run_id}_实验总结.md")
    hashes = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in persistent_paths
    }
    atomic_write_text(
        root / "checksums.sha256",
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
    )
    report = {
        "status": status, "run_id": run_id, "key_count": len(key_ids),
        "final_row_count": len(final_rows), "trajectory_row_count": len(trajectory_rows),
        "final_inversion_image_count": len(final_rows),
        "trajectory_unique_inversion_count": len({
            (row["condition_id"], row["key_id"], int(row["step"])) for row in trajectory_rows
        }),
        "validated_batching": config["validated_batching"],
        "spool_cleanup_status": "PENDING", "hashes": hashes,
    }
    atomic_write_json(report_path, report)
    if not _report_artifacts_are_valid(root, report):
        raise RuntimeError("Persistent evaluation artifact hash verification failed")
    report["spool_cleanup"] = _cleanup_validated_spools(root)
    report["spool_cleanup_status"] = "COMPLETE"
    atomic_write_json(report_path, report)
    _write_evaluation_progress(
        root, completed=len(attack_rows), total=len(attack_rows),
        durations=evaluation_durations, stage="complete",
    )
    return report


ATTACK_COPY_FIELDS = [
    "protocol_version", "run_id", "condition_id", "watermark", "model_setting",
    "task", "method", "key_id", "target_id", "reference_ids", "clean_ids",
    "N", "lambda", "beta", "gamma", "seed", "final_step", "output_sha256",
    "output_image_path",
]
