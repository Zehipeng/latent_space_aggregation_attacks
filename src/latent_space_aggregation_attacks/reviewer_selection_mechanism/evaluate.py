from __future__ import annotations

import itertools
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..core.atomic_io import atomic_write_json, atomic_write_text
from ..core.hashing import sha256_file, stable_hash
from ..core.seeds import configure_torch_determinism, derive_seed
from ..formal.attack import _encode
from ..formal.common import (
    adapter_config, assets_by_name, atomic_csv, canonical_512, formal_inputs,
    model_config, open_rgb, read_csv,
)
from ..formal.evaluate import _activations, _fid, _inception_model, _lpips_model
from ..latent_targets import fp32_mean
from ..models.loaders import load_proxy_vae, load_target_pipeline
from ..watermarks.base import registered_adapter
from . import MODEL_ORDER, PROTOCOL_VERSION, WATERMARK_ORDER
from .analysis import (
    clustered_spearman_ci, paired_strategy_differences, wilson_interval,
)
from .common import bool_value
from .conditions import condition_registry, validate_registry


def _evaluation_progress(
    root: Path, completed: int, total: int, started: float, stage: str,
) -> None:
    elapsed = time.perf_counter() - started
    per = elapsed / completed if completed else 0.0
    remaining = total - completed
    atomic_write_json(root / "progress.json", {
        "stage": stage, "completed_units": completed, "total_units": total,
        "remaining_units": remaining, "estimated_remaining_seconds": per * remaining,
        "estimated_completion_utc": (
            datetime.now(timezone.utc) + timedelta(seconds=per * remaining)
        ).isoformat(),
    })


def _quality(original: Any, attacked: Any, lpips_model: Any) -> dict[str, float]:
    import torch
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity

    first = np.asarray(original.convert("RGB"), dtype=np.float32) / 255.0
    second = np.asarray(attacked.convert("RGB"), dtype=np.float32) / 255.0
    a = torch.from_numpy(first).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(second).permute(2, 0, 1).unsqueeze(0)
    device = next(lpips_model.parameters()).device
    with torch.inference_mode():
        score = lpips_model(a.to(device) * 2 - 1, b.to(device) * 2 - 1)
    return {
        "lpips": float(score.squeeze().item()),
        "ssim": float(structural_similarity(
            first, second, data_range=1.0, channel_axis=2,
        )),
        "psnr": float(peak_signal_noise_ratio(first, second, data_range=1.0)),
    }


def _success(
    watermark: str, task: str, before: bool, after: bool,
    final_score: float, threshold: float,
) -> tuple[bool, bool, bool]:
    eligible = before if task == "removal" else not before
    if task == "forgery":
        success = eligible and after
    elif watermark == "gaussian_shading":
        success = eligible and not after
    else:
        success = eligible and final_score >= threshold
    equality = watermark != "gaussian_shading" and final_score == threshold
    return eligible, success, equality


def _margins(
    watermark: str, task: str, initial_score: float,
    final_score: float, threshold: float,
) -> dict[str, float]:
    if watermark == "gaussian_shading":
        initial_acceptance = initial_score - threshold
        final_acceptance = final_score - threshold
    else:
        initial_acceptance = threshold - initial_score
        final_acceptance = threshold - final_score
    return {
        "initial_acceptance_margin": initial_acceptance,
        "final_acceptance_margin": final_acceptance,
        "final_task_margin": (
            final_acceptance if task == "forgery" else -final_acceptance
        ),
        "score_change": final_score - initial_score,
    }


def _model_label(value: str) -> str:
    return "SDv1.4" if value.startswith("same_model") else "SDv2.0"


def _threshold(config: dict[str, Any], watermark: str) -> float:
    field = (
        "bit_accuracy_threshold"
        if watermark == "gaussian_shading" else "p_value_threshold"
    )
    return float(config["watermark_runtime"][watermark][field])


def _source(root: Path, path: str) -> Any:
    value = Path(path)
    image = open_rgb(value if value.is_absolute() else root / value)
    return canonical_512(image)


def _direction_feature_controls(
    *, root: Path, config: dict[str, Any], assets: dict[str, dict[str, Any]],
    inception: Any,
) -> list[dict[str, Any]]:
    import torch
    import torch.nn.functional as functional

    candidates: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(root / "manifests/candidate_bank_manifest.csv"):
        candidates[(row["model_setting"], row["watermark"], row["key_id"])].append(row)
    selections: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(root / "manifests/reference_selection_manifest.csv"):
        selections[(row["model_setting"], row["watermark"], row["key_id"], row["selection_strategy"])].append(row)
    controls = {
        (row["model_setting"], row["watermark"], row["key_id"], row["selection_strategy"]): row
        for row in json.loads((root / "evaluation/direction_controls.json").read_text(encoding="utf-8"))
    }
    _, _, clean = formal_inputs(assets)
    feature_rows: list[dict[str, Any]] = []
    candidate_groups = sorted(candidates.items())
    for group_index, (group, bank) in enumerate(candidate_groups, start=1):
        model, watermark, key_id = group
        bank.sort(key=lambda row: int(row["candidate_index"]))
        clean_rows = clean[key_id]
        candidate_features = _activations(
            inception, [root / row["image_path"] for row in bank], batch_size=16,
        )
        clean_features = _activations(
            inception, [row["path"] for row in clean_rows], batch_size=16,
        )
        for selection_key, selected in selections.items():
            if selection_key[:3] != group:
                continue
            strategy = selection_key[3]
            indices = [int(row["candidate_index"]) for row in selected]
            centre = candidate_features[indices].mean(axis=0)
            distances = np.linalg.norm(clean_features - centre[None, :], axis=1)
            order = np.argsort(distances, kind="mergesort")
            nearest, farthest = sorted(order[:5].tolist()), sorted(order[-5:].tolist())
            feature_rows.append({
                "model_setting": model, "watermark": watermark,
                "key_id": key_id, "selection_strategy": strategy,
                "matched_control": "inception_feature_matched",
                "clean_indices": ";".join(map(str, nearest)),
                "mean_feature_distance": float(distances[nearest].mean()),
                "centroid_tensor_path": controls[selection_key]["centroid_tensor_path"],
            })
            feature_rows.append({
                "model_setting": model, "watermark": watermark,
                "key_id": key_id, "selection_strategy": strategy,
                "matched_control": "inception_feature_mismatched",
                "clean_indices": ";".join(map(str, farthest)),
                "mean_feature_distance": float(distances[farthest].mean()),
                "centroid_tensor_path": controls[selection_key]["centroid_tensor_path"],
            })
        atomic_write_json(root / "progress.json", {
            "stage": "evaluate_e4_inception_controls",
            "completed_groups": group_index,
            "total_groups": len(candidate_groups),
            "current_model_setting": model,
            "current_watermark": watermark, "current_key_id": key_id,
        })

    # Add proxy-latent direction quantities without detector access.
    for model_setting in MODEL_ORDER:
        vae = load_proxy_vae(model_config(assets, model_setting), offline=True)
        model_rows = [row for row in feature_rows if row["model_setting"] == model_setting]
        clean_cache: dict[str, Any] = {}
        for row_index, row in enumerate(model_rows, start=1):
            key_id = row["key_id"]
            if key_id not in clean_cache:
                clean_cache[key_id] = _encode(
                    vae,
                    [canonical_512(open_rgb(item["path"])) for item in clean[key_id]],
                    batch_size=int(config["reference_encode_batch_size"]),
                ).float()
            payload = torch.load(root / row["centroid_tensor_path"], map_location="cpu")
            same = payload["same_key_centroid"].float()
            values = clean_cache[key_id]
            indices = [int(value) for value in row["clean_indices"].split(";")]
            direction = same - fp32_mean(values[indices]).cpu()
            main = same - fp32_mean(
                values[:int(config["clean_reference_count"])]
            ).cpu()
            row["direction_norm"] = float(direction.norm().item())
            row["cosine_to_main_direction"] = float(
                functional.cosine_similarity(
                    direction.flatten(), main.flatten(), dim=0,
                ).item()
            )
            if row_index % 8 == 0 or row_index == len(model_rows):
                atomic_write_json(root / "progress.json", {
                    "stage": "evaluate_e4_latent_direction_controls",
                    "model_setting": model_setting,
                    "completed_rows": row_index,
                    "total_rows_for_model": len(model_rows),
                })
        del vae
        torch.cuda.empty_cache()
    return feature_rows


def evaluate(
    config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
    key_ids: list[str], smoke: bool,
) -> dict[str, Any]:
    import torch

    report_path = root / ("smoke_report.json" if smoke else "evaluation_report.json")
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch)
    started = time.perf_counter()
    assets = assets_by_name(lock)
    conditions = condition_registry()
    validate_registry(conditions)
    attacks = read_csv(root / "manifests/attack_outputs.csv")
    originals = {
        (row["model_setting"], row["watermark"], row["task"], row["key_id"]): row
        for row in read_csv(root / "evaluation/original_detection.csv")
    }
    latent_rows = read_csv(root / "evaluation/mechanism_latent_trajectory.csv")
    latent_by_group: dict[tuple[str, str], dict[str, str]] = {
        (row["unit_id"], row["step"]): row for row in latent_rows
    }
    final_dir = root / "evaluation/final_units"
    trajectory_dir = root / "evaluation/trajectory_units"
    final_dir.mkdir(parents=True, exist_ok=True)
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    lpips_model = _lpips_model(assets)
    detector_total = len(attacks) * 5
    detector_completed = len(list(final_dir.glob("*.json"))) + len(
        list(trajectory_dir.glob("*.json"))
    )

    for model_setting in MODEL_ORDER:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in WATERMARK_ORDER:
            adapter = registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            threshold = _threshold(config, watermark)
            for attack in sorted(
                [row for row in attacks
                 if row["model_setting"] == model_setting and row["watermark"] == watermark],
                key=lambda row: (row["condition_id"], row["key_id"]),
            ):
                unit = attack["condition_id"] + "|" + attack["key_id"]
                key = adapter.create_key({
                    "key_id": attack["key_id"],
                    "watermark_seed": derive_seed(
                        "watermark_key", watermark, attack["key_id"],
                    ),
                })
                before = originals[(model_setting, watermark, attack["task"], attack["key_id"])]
                accepted_before = bool_value(before["accepted_before"])
                initial_score = float(before["initial_score"])

                final_path = final_dir / f"{stable_hash(unit)}.json"
                if not final_path.is_file():
                    output = root / attack["output_image_path"]
                    if sha256_file(output) != attack["output_sha256"]:
                        raise RuntimeError(f"attack SHA mismatch: {output}")
                    attacked = open_rgb(output)
                    detected = adapter.detect(attacked, key)
                    eligible, success, equality = _success(
                        watermark, attack["task"], accepted_before,
                        detected.accepted, float(detected.score), threshold,
                    )
                    row = {
                        **attack, "eligible": eligible, "success": success,
                        "initial_score": initial_score,
                        "final_score": float(detected.score),
                        "score_name": detected.score_name,
                        "accepted_before": accepted_before,
                        "accepted_after": bool(detected.accepted),
                        "threshold": threshold, "threshold_equality": equality,
                        **_margins(
                            watermark, attack["task"], initial_score,
                            float(detected.score), threshold,
                        ),
                        **_quality(
                            _source(root, attack["source_path"]), attacked, lpips_model,
                        ),
                    }
                    atomic_write_json(final_path, row)
                    detector_completed += 1
                    _evaluation_progress(
                        root, detector_completed, detector_total, started,
                        "evaluate_detectors_and_quality",
                    )

                for step in (0, 50, 100, 150):
                    trajectory_path = trajectory_dir / f"{stable_hash(unit + '|' + str(step))}.json"
                    if trajectory_path.is_file():
                        continue
                    latent = latent_by_group[(unit, str(step))]
                    checkpoint = root / latent["checkpoint_image_path"]
                    if sha256_file(checkpoint) != latent["checkpoint_sha256"]:
                        raise RuntimeError(f"checkpoint SHA mismatch: {checkpoint}")
                    detected = adapter.detect(open_rgb(checkpoint), key)
                    atomic_write_json(trajectory_path, {
                        **latent, "detector_score": float(detected.score),
                        "score_name": detected.score_name,
                        "accepted": bool(detected.accepted), "threshold": threshold,
                        **_margins(
                            watermark, attack["task"], initial_score,
                            float(detected.score), threshold,
                        ),
                    })
                    detector_completed += 1
                    _evaluation_progress(
                        root, detector_completed, detector_total, started,
                        "evaluate_detectors_and_quality",
                    )
            del adapter
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()

    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(final_dir.glob("*.json"))]
    trajectory = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(trajectory_dir.glob("*.json"))
    ]
    if len(rows) != len(attacks) or len(trajectory) != len(attacks) * 4:
        raise RuntimeError("final or trajectory evaluation is incomplete")
    atomic_csv(root / "evaluation/final_per_key_metrics.csv", rows)
    atomic_csv(root / "evaluation/mechanism_detector_trajectory.csv", trajectory)

    inception = _inception_model(assets["inception-v3-imagenet1k"]["path"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition_id"]].append(row)
    source_features: dict[tuple[str, str, str], Any] = {}
    fid_by_condition: dict[str, float] = {}
    for condition_id, group in sorted(grouped.items()):
        group.sort(key=lambda row: row["key_id"])
        first = group[0]
        source_key = (first["model_setting"], first["watermark"], first["task"])
        if source_key not in source_features:
            source_features[source_key] = _activations(
                inception,
                [
                    root / row["source_path"]
                    if not Path(row["source_path"]).is_absolute()
                    else row["source_path"]
                    for row in group
                ],
            )
        attacked_features = _activations(
            inception, [root / row["output_image_path"] for row in group],
        )
        fid_by_condition[condition_id] = _fid(
            source_features[source_key], attacked_features,
        )

    feature_controls = _direction_feature_controls(
        root=root, config=config, assets=assets, inception=inception,
    )
    atomic_csv(root / "evaluation/e4_feature_controls.csv", feature_controls)
    del inception, lpips_model
    torch.cuda.empty_cache()

    summaries: list[dict[str, Any]] = []
    for condition_id, group in sorted(grouped.items()):
        first = group[0]
        eligible = [row for row in group if row["eligible"] is True]
        successes = sum(row["success"] is True for row in eligible)
        interval = wilson_interval(successes, len(eligible)) if eligible else ("", "")
        summaries.append({
            "protocol_version": PROTOCOL_VERSION, "run_id": run_id,
            "condition_id": condition_id,
            "Watermark": first["watermark"],
            "Model": _model_label(first["model_setting"]),
            "Task": first["task"],
            "selection_strategy": first["selection_strategy"],
            "sample_n": len(group), "eligible_n": len(eligible),
            "success_n": successes,
            "ASR": successes / len(eligible) if eligible else "",
            "ASR_CI95_low": interval[0], "ASR_CI95_high": interval[1],
            "LPIPS": float(np.mean([float(row["lpips"]) for row in group])),
            "SSIM": float(np.mean([float(row["ssim"]) for row in group])),
            "PSNR": float(np.mean([float(row["psnr"]) for row in group])),
            "FID": fid_by_condition[condition_id],
            "Time": float(np.mean([
                float(row["optimization_compute_time"]) for row in group
            ])),
            "InitialScore": float(np.mean([float(row["initial_score"]) for row in group])),
            "FinalScore": float(np.mean([float(row["final_score"]) for row in group])),
            "ThresholdMargin": float(np.mean([
                float(row["final_task_margin"]) for row in group
            ])),
        })
    atomic_csv(root / "evaluation/e2_condition_summary.csv", summaries)

    paired: list[dict[str, Any]] = []
    strategies = sorted({row["selection_strategy"] for row in rows})
    for (model, watermark, task), group_iter in itertools.groupby(
        sorted(rows, key=lambda row: (
            row["model_setting"], row["watermark"], row["task"],
        )),
        key=lambda row: (row["model_setting"], row["watermark"], row["task"]),
    ):
        group = list(group_iter)
        for first, second in itertools.combinations(strategies, 2):
            for metric, transform in (
                ("success", lambda row: float(row["success"] is True)),
                ("final_task_margin", None),
            ):
                available = {row["selection_strategy"] for row in group}
                if first not in available or second not in available:
                    continue
                first_keys = {
                    row["key_id"] for row in group
                    if row["selection_strategy"] == first
                }
                second_keys = {
                    row["key_id"] for row in group
                    if row["selection_strategy"] == second
                }
                if not first_keys.intersection(second_keys):
                    continue
                result = paired_strategy_differences(
                    group, strategy_a=first, strategy_b=second,
                    metric=metric, transform=transform,
                    seed=derive_seed("reviewer_selection", model, watermark, task, first, second, metric),
                )
                paired.append({
                    "model_setting": model, "watermark": watermark,
                    "task": task, **result,
                })
    atomic_csv(root / "evaluation/e2_paired_strategy_comparisons.csv", paired)

    correlations: list[dict[str, Any]] = []
    for group_key, group_iter in itertools.groupby(
        sorted(trajectory, key=lambda row: (
            row["model_setting"], row["watermark"], row["task"],
            row["selection_strategy"],
        )),
        key=lambda row: (
            row["model_setting"], row["watermark"], row["task"],
            row["selection_strategy"],
        ),
    ):
        group = list(group_iter)
        for distance in (
            "distance_to_target", "distance_to_same_key_centroid",
            "distance_to_shuffled_key_centroid", "distance_to_clean_centroid",
        ):
            for outcome in ("detector_score", "final_task_margin"):
                estimate, low, high, cluster_n = clustered_spearman_ci(
                    group, distance, outcome,
                    seed=derive_seed("reviewer_selection", *group_key, distance, outcome),
                )
                correlations.append({
                    "model_setting": group_key[0], "watermark": group_key[1],
                    "task": group_key[2], "selection_strategy": group_key[3],
                    "distance_variable": distance, "outcome_variable": outcome,
                    "spearman_rho": estimate, "cluster_bootstrap_ci95_low": low,
                    "cluster_bootstrap_ci95_high": high,
                    "key_cluster_n": cluster_n, "row_n": len(group),
                    "bootstrap_replicates": 2000,
                })
    atomic_csv(root / "evaluation/e4_clustered_correlations.csv", correlations)

    summary_path = root / f"{run_id}_实验总结.md"
    atomic_write_text(summary_path, "\n".join([
        "# E2参考选择与E4机制实验总结", "",
        f"- 状态：{'SMOKE_PASSED' if smoke else 'COMPLETE'}",
        f"- 协议：{PROTOCOL_VERSION}", f"- run_id：{run_id}",
        f"- 最终攻击输出：{len(rows)}", f"- 机制检查点：{len(trajectory)}",
        "- E2：四种新增参考选择策略，按密钥配对比较。",
        "- E4：同密钥/错密钥/干净中心、干净子集、Inception特征匹配控制及聚类bootstrap相关性。",
        "- 相关性仅作为关联证据，不作为因果证明。", "",
    ]))

    persistent = [
        root / "attack_report.json", root / "preparation_report.json",
        root / "evaluation/final_per_key_metrics.csv",
        root / "evaluation/e2_condition_summary.csv",
        root / "evaluation/e2_paired_strategy_comparisons.csv",
        root / "evaluation/mechanism_latent_trajectory.csv",
        root / "evaluation/mechanism_detector_trajectory.csv",
        root / "evaluation/e4_clustered_correlations.csv",
        root / "evaluation/e4_feature_controls.csv",
        root / "evaluation/direction_controls.json",
        root / "evaluation/original_detection.csv",
        root / "manifests/run_manifest.json",
        root / "manifests/key_manifest.json",
        root / "manifests/candidate_bank_manifest.csv",
        root / "manifests/reference_selection_manifest.csv",
        root / "manifests/ineligible_selection_groups.csv",
        root / "manifests/pool_feasibility.csv",
        root / "manifests/common_source_manifest.csv",
        root / "manifests/clean_prior_manifest.csv",
        root / "manifests/clean_subset_manifest.csv",
        root / "manifests/shuffled_key_control.csv",
        root / "manifests/attack_outputs.csv",
        root / "protocol_snapshot/config_resolved.json",
        root / "protocol_snapshot/assets.lock.json",
        root / "protocol_snapshot/source_config.yaml",
        root / "protocol_snapshot/reviewer_selection_mechanism_v1.0.md",
        summary_path,
    ]
    atomic_write_text(root / "checksums.sha256", "\n".join(
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in persistent
    ) + "\n")

    temporary = [
        path for base in (root / "prepared_inputs", root / "evaluation_spool")
        for path in base.rglob("*") if path.is_file()
    ]
    removed_bytes = sum(path.stat().st_size for path in temporary)
    for path in temporary:
        path.unlink()
    for base in (root / "prepared_inputs", root / "evaluation_spool"):
        for directory in sorted(
            (path for path in base.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts), reverse=True,
        ):
            directory.rmdir()
    cleanup = {
        "status": "COMPLETE", "removed_files": len(temporary),
        "removed_bytes": removed_bytes,
    }
    atomic_write_json(root / "logs/temporary_artifact_cleanup.json", cleanup)
    report = {
        "status": "PASSED" if smoke else "COMPLETE",
        "protocol_version": PROTOCOL_VERSION,
        "final_row_count": len(rows), "summary_row_count": len(summaries),
        "trajectory_row_count": len(trajectory),
        "spool_cleanup_status": "COMPLETE",
        "elapsed_seconds": time.perf_counter() - started,
    }
    atomic_write_json(report_path, report)
    return report
