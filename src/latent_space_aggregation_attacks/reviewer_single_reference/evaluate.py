from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from ..core.atomic_io import atomic_write_json, atomic_write_text
from ..core.hashing import sha256_file, stable_hash
from ..core.seeds import configure_torch_determinism, derive_seed
from ..formal.common import (
    adapter_config, assets_by_name, atomic_csv, canonical_512,
    model_config, open_rgb, read_csv,
)
from ..formal.evaluate import _activations, _fid, _inception_model, _lpips_model
from ..models.loaders import load_target_pipeline
from ..watermarks.base import registered_adapter
from . import MODEL_ORDER, PROTOCOL_VERSION, WATERMARK_ORDER
from .conditions import condition_registry, validate_registry


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
    equality = bool(
        watermark != "gaussian_shading" and final_score == threshold
    )
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
    task_margin = final_acceptance if task == "forgery" else -final_acceptance
    return {
        "initial_acceptance_margin": initial_acceptance,
        "final_acceptance_margin": final_acceptance,
        "final_task_margin": task_margin,
        "score_change": final_score - initial_score,
    }


def _model_label(model_setting: str) -> str:
    return "SDv1.4" if model_setting.startswith("same_model") else "SDv2.0"


def _write_reporting_tables(
    root: Path, summaries: list[dict[str, Any]],
) -> None:
    table_dir = root / "evaluation/tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    atomic_csv(table_dir / "single_reference_N_clean_table.csv", [
        row for row in summaries
        if float(row["lambda_pixel"]) == 20000.0
        and float(row["beta"]) == 1.5
    ])
    atomic_csv(table_dir / "single_reference_lambda_table.csv", [
        row for row in summaries
        if int(row["N_clean"]) == 5
        and float(row["beta"]) == 1.5
    ])
    atomic_csv(table_dir / "single_reference_beta_table.csv", [
        row for row in summaries
        if row["Task"] == "removal"
        and int(row["N_clean"]) == 5
        and float(row["lambda_pixel"]) == 20000.0
    ])


def evaluate(
    config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
    key_ids: list[str], smoke: bool,
) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch)
    started = time.perf_counter()
    assets = assets_by_name(lock)
    conditions = condition_registry()
    validate_registry(conditions)
    attacks = read_csv(root / "manifests/attack_outputs.csv")
    expected = len(conditions) * len(key_ids)
    if len(attacks) != expected:
        raise RuntimeError(f"expected {expected} attacks, found {len(attacks)}")
    originals = {
        (row["model_setting"], row["watermark"], row["task"], row["key_id"]): row
        for row in read_csv(root / "evaluation/original_detection.csv")
    }
    unit_dir = root / "evaluation/final_units"
    unit_dir.mkdir(parents=True, exist_ok=True)
    lpips_model = _lpips_model(assets)

    for model_setting in MODEL_ORDER:
        pipe = load_target_pipeline(model_config(assets, model_setting), offline=True)
        for watermark in WATERMARK_ORDER:
            adapter = registered_adapter(
                watermark, adapter_config(config, watermark, pipe, assets),
            )
            runtime = config["watermark_runtime"][watermark]
            threshold = float(runtime[
                "bit_accuracy_threshold"
                if watermark == "gaussian_shading"
                else "p_value_threshold"
            ])
            model_attacks = [
                row for row in attacks
                if row["model_setting"] == model_setting
                and row["watermark"] == watermark
            ]
            for attack in sorted(
                model_attacks,
                key=lambda row: (row["condition_id"], row["key_id"]),
            ):
                unit_id = attack["condition_id"] + "|" + attack["key_id"]
                record_path = unit_dir / f"{stable_hash(unit_id)}.json"
                if record_path.is_file():
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    if record.get("output_sha256") == attack["output_sha256"]:
                        continue
                output = root / attack["output_image_path"]
                if sha256_file(output) != attack["output_sha256"]:
                    raise RuntimeError("attack SHA mismatch")
                key_id, task = attack["key_id"], attack["task"]
                key = adapter.create_key({
                    "key_id": key_id,
                    "watermark_seed": derive_seed("watermark_key", watermark, key_id),
                })
                attacked = open_rgb(output)
                detected = adapter.detect(attacked, key)
                before = originals[(model_setting, watermark, task, key_id)]
                accepted_before = str(before["accepted_before"]).lower() == "true"
                eligible, success, equality = _success(
                    watermark, task, accepted_before, detected.accepted,
                    detected.score, threshold,
                )
                source_path = Path(attack["source_path"])
                source = (
                    open_rgb(root / source_path)
                    if not source_path.is_absolute()
                    else canonical_512(open_rgb(source_path))
                )
                initial_score = float(before["initial_score"])
                row = {
                    **attack,
                    "eligible": eligible,
                    "success": success,
                    "initial_score": initial_score,
                    "final_score": detected.score,
                    "score_name": detected.score_name,
                    "accepted_before": accepted_before,
                    "accepted_after": detected.accepted,
                    "threshold": threshold,
                    "threshold_equality": equality,
                    **_margins(
                        watermark, task, initial_score,
                        float(detected.score), threshold,
                    ),
                    **_quality(source, attacked, lpips_model),
                }
                atomic_write_json(record_path, row)
            del adapter
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()

    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(unit_dir.glob("*.json"))
    ]
    if len(rows) != expected:
        raise RuntimeError(f"expected {expected} final rows, found {len(rows)}")
    final_path = root / "evaluation/final_per_key_metrics.csv"
    atomic_csv(final_path, rows)

    inception = _inception_model(assets["inception-v3-imagenet1k"]["path"])
    source_features: dict[tuple[str, str, str], Any] = {}
    fid_by_condition: dict[str, float] = {}
    fid_dir = root / "evaluation/fid_units"
    fid_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["condition_id"]].append(row)
    for condition_id, group in sorted(grouped.items()):
        group = sorted(group, key=lambda row: row["key_id"])
        first = group[0]
        source_group = (
            first["model_setting"], first["watermark"], first["task"],
        )
        source_paths = [
            root / row["source_path"]
            if not Path(row["source_path"]).is_absolute()
            else row["source_path"]
            for row in group
        ]
        attacked_paths = [root / row["output_image_path"] for row in group]
        collection_hash = stable_hash({
            "sources": [str(path) for path in source_paths],
            "outputs": [row["output_sha256"] for row in group],
        })
        fid_record_path = fid_dir / f"{stable_hash(condition_id)}.json"
        if fid_record_path.is_file():
            record = json.loads(fid_record_path.read_text(encoding="utf-8"))
            if record.get("collection_hash") == collection_hash:
                fid_by_condition[condition_id] = float(record["FID"])
                continue
        if source_group not in source_features:
            source_features[source_group] = _activations(inception, source_paths)
        attacked_features = _activations(inception, attacked_paths)
        fid = _fid(source_features[source_group], attacked_features)
        fid_by_condition[condition_id] = fid
        atomic_write_json(fid_record_path, {
            "condition_id": condition_id,
            "collection_hash": collection_hash,
            "sample_n": len(group),
            "FID": fid,
        })
    del inception, lpips_model
    torch.cuda.empty_cache()

    summaries: list[dict[str, Any]] = []
    for condition_id, group in sorted(grouped.items()):
        first = group[0]
        eligible = [row for row in group if row["eligible"] is True]
        summaries.append({
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "condition_id": condition_id,
            "Watermark": first["watermark"],
            "Model": _model_label(first["model_setting"]),
            "Task": first["task"],
            "N_watermarked": int(first["N_watermarked"]),
            "N_clean": int(first["N_clean"]),
            "lambda_pixel": float(first["lambda_pixel"]),
            "beta": float(first["beta"]),
            "sample_n": len(group),
            "eligible_n": len(eligible),
            "success_n": sum(row["success"] is True for row in eligible),
            "ASR": (
                sum(row["success"] is True for row in eligible) / len(eligible)
                if eligible else ""
            ),
            "LPIPS": float(np.mean([row["lpips"] for row in group])),
            "SSIM": float(np.mean([row["ssim"] for row in group])),
            "PSNR": float(np.mean([row["psnr"] for row in group])),
            "FID": fid_by_condition[condition_id],
            "Time": float(np.mean([
                float(row["optimization_compute_time"]) for row in group
            ])),
            "InitialScore": float(np.mean([row["initial_score"] for row in group])),
            "FinalScore": float(np.mean([row["final_score"] for row in group])),
            "ThresholdMargin": float(np.mean([
                row["final_task_margin"] for row in group
            ])),
        })
    atomic_csv(root / "evaluation/final_condition_summary.csv", summaries)
    _write_reporting_tables(root, summaries)
    atomic_csv(
        root / "evaluation/failed_samples.csv",
        [row for row in rows if row["eligible"] is True and row["success"] is False],
        list(rows[0]),
    )
    atomic_csv(
        root / "evaluation/ineligible_samples.csv",
        [row for row in rows if row["eligible"] is False],
        list(rows[0]),
    )

    summary_md = root / f"{run_id}_实验总结.md"
    atomic_write_text(summary_md, "\n".join([
        "# 单水印参考完整补充实验总结",
        "",
        f"- 状态：{'SMOKE_PASSED' if smoke else 'COMPLETE'}",
        f"- 协议：{PROTOCOL_VERSION}",
        f"- run_id：{run_id}",
        f"- 样本：{len(key_ids)} keys，{len(rows)} 个最终攻击输出",
        f"- 条件：{len(conditions)} 个去重后的单因素条件",
        "- 设置：固定1张同密钥水印图；N_clean、lambda及移除beta分别变化；覆盖同模型与跨模型。",
        "- 指标：ASR、LPIPS、SSIM、PSNR、FID、Time及连续检测分数/阈值边距。",
        "",
        "最终数值以 evaluation/final_per_key_metrics.csv 与 evaluation/final_condition_summary.csv 为准。",
        "低ASR是实验结果，不构成流程失败。",
        "",
    ]))

    persistent = [
        root / "attack_report.json",
        root / "preparation_report.json",
        final_path,
        root / "evaluation/final_condition_summary.csv",
        root / "evaluation/failed_samples.csv",
        root / "evaluation/ineligible_samples.csv",
        root / "evaluation/original_detection.csv",
        root / "evaluation/tables/single_reference_N_clean_table.csv",
        root / "evaluation/tables/single_reference_lambda_table.csv",
        root / "evaluation/tables/single_reference_beta_table.csv",
        root / "manifests/run_manifest.json",
        root / "manifests/key_manifest.json",
        root / "manifests/reference_manifest.csv",
        root / "manifests/clean_prior_manifest.csv",
        root / "manifests/reference_candidate_manifest.csv",
        root / "manifests/reference_selection_control.csv",
        root / "manifests/sample_manifest.csv",
        root / "manifests/attack_outputs.csv",
        root / "protocol_snapshot/config_resolved.json",
        root / "protocol_snapshot/assets.lock.json",
        root / "protocol_snapshot/source_config.yaml",
        root / "protocol_snapshot/reviewer_single_reference_v1.0.md",
        summary_md,
    ]
    checksum_lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in persistent
    ]
    atomic_write_text(root / "checksums.sha256", "\n".join(checksum_lines) + "\n")

    temporary = [
        path
        for base in (root / "prepared_inputs", root / "evaluation_spool")
        for path in base.rglob("*.png")
    ]
    removed_bytes = sum(path.stat().st_size for path in temporary)
    for path in temporary:
        path.unlink()
    for base in (root / "prepared_inputs", root / "evaluation_spool"):
        if base.exists():
            for directory in sorted(
                (path for path in base.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts), reverse=True,
            ):
                directory.rmdir()
    cleanup = {
        "status": "COMPLETE",
        "removed_files": len(temporary),
        "removed_bytes": removed_bytes,
    }
    atomic_write_json(root / "logs/png_cleanup.json", cleanup)
    report = {
        "status": "PASSED" if smoke else "COMPLETE",
        "protocol_version": PROTOCOL_VERSION,
        "final_row_count": len(rows),
        "summary_row_count": len(summaries),
        "spool_cleanup_status": "COMPLETE",
        "elapsed_seconds": time.perf_counter() - started,
    }
    atomic_write_json(
        root / ("smoke_report.json" if smoke else "evaluation_report.json"),
        report,
    )
    return report
