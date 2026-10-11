from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from ..core.atomic_io import atomic_write_json, atomic_write_text
from ..core.hashing import sha256_file
from ..core.seeds import configure_torch_determinism, derive_seed
from ..formal.common import (adapter_config, assets_by_name, atomic_csv, canonical_512,
                             model_config, open_rgb, read_csv)
from ..formal.evaluate import _activations, _fid, _inception_model, _lpips_model
from ..models.loaders import load_target_pipeline
from ..watermarks.base import registered_adapter
from . import PROTOCOL_VERSION, WATERMARK_ORDER


def _quality(original: Any, attacked: Any, lpips_model: Any) -> dict[str, float]:
    import torch
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity
    first = np.asarray(original.convert("RGB"), dtype=np.float32) / 255.0
    second = np.asarray(attacked.convert("RGB"), dtype=np.float32) / 255.0
    a = torch.from_numpy(first).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(second).permute(2, 0, 1).unsqueeze(0)
    device = next(lpips_model.parameters()).device
    with torch.inference_mode(): score = lpips_model(a.to(device)*2-1, b.to(device)*2-1)
    return {"lpips": float(score.squeeze().item()),
            "ssim": float(structural_similarity(first, second, data_range=1.0, channel_axis=2)),
            "psnr": float(peak_signal_noise_ratio(first, second, data_range=1.0))}


def _success(watermark: str, task: str, before: bool, after: bool,
             final_score: float, threshold: float) -> tuple[bool, bool, bool]:
    eligible = before if task == "removal" else not before
    if task == "forgery": success = eligible and after
    elif watermark == "gaussian_shading": success = eligible and not after
    else: success = eligible and final_score >= threshold
    return eligible, success, bool(watermark != "gaussian_shading" and final_score == threshold)


def evaluate(config: dict[str, Any], lock: dict[str, Any], root: Path, run_id: str,
             key_ids: list[str], smoke: bool) -> dict[str, Any]:
    import torch
    if not torch.cuda.is_available(): raise RuntimeError("CUDA is required")
    configure_torch_determinism(torch); started = time.perf_counter()
    assets = assets_by_name(lock); attacks = read_csv(root / "manifests/attack_outputs.csv")
    expected = len(key_ids) * 6
    if len(attacks) != expected: raise RuntimeError(f"expected {expected} attacks, found {len(attacks)}")
    originals = {(row["watermark"], row["task"], row["key_id"]): row
                 for row in read_csv(root / "evaluation/original_detection.csv")}
    pipe = load_target_pipeline(model_config(assets, config["model_setting"]), offline=True)
    lpips_model = _lpips_model(assets); rows: list[dict[str, Any]] = []
    for watermark in WATERMARK_ORDER:
        adapter = registered_adapter(watermark, adapter_config(config, watermark, pipe, assets))
        runtime = config["watermark_runtime"][watermark]
        threshold = float(runtime["bit_accuracy_threshold" if watermark == "gaussian_shading" else "p_value_threshold"])
        for attack in [row for row in attacks if row["watermark"] == watermark]:
            key_id, task = attack["key_id"], attack["task"]
            key = adapter.create_key({"key_id": key_id,
                "watermark_seed": derive_seed("watermark_key", watermark, key_id)})
            output = root / attack["output_image_path"]
            if sha256_file(output) != attack["output_sha256"]: raise RuntimeError("attack SHA mismatch")
            attacked = open_rgb(output); detected = adapter.detect(attacked, key)
            before = originals[(watermark, task, key_id)]
            accepted_before = str(before["accepted_before"]).lower() == "true"
            eligible, success, equality = _success(watermark, task, accepted_before,
                                                    detected.accepted, detected.score, threshold)
            source_path = Path(attack["source_path"])
            source = open_rgb(root / source_path) if not source_path.is_absolute() else canonical_512(open_rgb(source_path))
            quality = _quality(source, attacked, lpips_model)
            rows.append({**attack, "eligible": eligible, "success": success,
                "initial_score": before["initial_score"], "final_score": detected.score,
                "score_name": detected.score_name, "accepted_before": accepted_before,
                "accepted_after": detected.accepted, "threshold": threshold,
                "threshold_equality": equality, **quality})
        del adapter; torch.cuda.empty_cache()
    final_path = root / "evaluation/final_per_key_metrics.csv"; atomic_csv(final_path, rows)
    inception = _inception_model(assets["inception-v3-imagenet1k"]["path"])
    fids: dict[tuple[str, str], float] = {}
    for watermark in WATERMARK_ORDER:
        for task in ("removal", "forgery"):
            group = sorted([row for row in rows if row["watermark"] == watermark and row["task"] == task],
                           key=lambda row: row["key_id"])
            first = _activations(inception, [root / row["source_path"] if not Path(row["source_path"]).is_absolute()
                                             else row["source_path"] for row in group])
            second = _activations(inception, [root / row["output_image_path"] for row in group])
            fids[(watermark, task)] = _fid(first, second)
    del inception, lpips_model, pipe; torch.cuda.empty_cache()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows: grouped[(row["watermark"], row["task"])].append(row)
    summaries = []
    for (watermark, task), group in sorted(grouped.items()):
        eligible = [row for row in group if row["eligible"] is True]
        summaries.append({"protocol_version": PROTOCOL_VERSION, "run_id": run_id,
            "Watermark": watermark, "Model": "SDv2.0", "Task": task,
            "sample_n": len(group), "eligible_n": len(eligible),
            "success_n": sum(row["success"] is True for row in eligible),
            "ASR": sum(row["success"] is True for row in eligible)/len(eligible) if eligible else "",
            "LPIPS": float(np.mean([row["lpips"] for row in group])),
            "SSIM": float(np.mean([row["ssim"] for row in group])),
            "PSNR": float(np.mean([row["psnr"] for row in group])),
            "FID": fids[(watermark, task)],
            "Time": float(np.mean([float(row["optimization_compute_time"]) for row in group]))})
    atomic_csv(root / "evaluation/final_condition_summary.csv", summaries)
    atomic_csv(root / "evaluation/failed_samples.csv", [row for row in rows if row["eligible"] is True and row["success"] is False], list(rows[0]))
    atomic_csv(root / "evaluation/ineligible_samples.csv", [row for row in rows if row["eligible"] is False], list(rows[0]))
    summary_md = root / f"{run_id}_实验总结.md"
    atomic_write_text(summary_md, "\n".join([
        "# 受限访问补充实验总结", "", f"- 状态：{'SMOKE_PASSED' if smoke else 'COMPLETE'}",
        f"- 协议：{PROTOCOL_VERSION}", f"- run_id：{run_id}",
        f"- 样本：{len(key_ids)} keys，{len(rows)} 个最终攻击输出",
        "- 设置：1 张同密钥水印图、5 张非配对干净图、仅 SDv2.0→SDv1.4 跨模型",
        "- 指标：ASR、LPIPS、SSIM、PSNR、FID、Time（未计算 L2/L∞）", "",
        "最终数值以 evaluation/final_per_key_metrics.csv 与 evaluation/final_condition_summary.csv 为准。",
        "Tree-Ring、RingID 与 Gaussian Shading 的低 ASR 均视为实验结果，不构成流程失败。", "",
    ]))
    persistent = [root / "attack_report.json", root / "preparation_report.json", final_path,
                  root / "evaluation/final_condition_summary.csv", root / "evaluation/failed_samples.csv",
                  root / "evaluation/ineligible_samples.csv", root / "evaluation/original_detection.csv",
                  root / "manifests/run_manifest.json", root / "manifests/key_manifest.json",
                  root / "manifests/reference_manifest.csv", root / "manifests/clean_prior_manifest.csv",
                  root / "manifests/reference_candidate_manifest.csv",
                  root / "manifests/reference_selection_control.csv", root / "manifests/sample_manifest.csv",
                  root / "manifests/attack_outputs.csv", root / "protocol_snapshot/config_resolved.json",
                  root / "protocol_snapshot/assets.lock.json", root / "protocol_snapshot/source_config.yaml",
                  root / "protocol_snapshot/limited_access_v1.0.md", summary_md]
    checksum_lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in persistent]
    atomic_write_text(root / "checksums.sha256", "\n".join(checksum_lines) + "\n")
    temporary = [path for base in (root / "prepared_inputs", root / "evaluation_spool")
                 for path in base.rglob("*.png")]
    removed_bytes = sum(path.stat().st_size for path in temporary)
    for path in temporary: path.unlink()
    for base in (root / "prepared_inputs", root / "evaluation_spool"):
        if base.exists():
            for directory in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                directory.rmdir()
    cleanup = {"status": "COMPLETE", "removed_files": len(temporary), "removed_bytes": removed_bytes}
    atomic_write_json(root / "logs/png_cleanup.json", cleanup)
    report = {"status": "PASSED" if smoke else "COMPLETE", "protocol_version": PROTOCOL_VERSION,
              "final_row_count": len(rows), "summary_row_count": len(summaries),
              "spool_cleanup_status": "COMPLETE", "elapsed_seconds": time.perf_counter()-started,
              "prohibited_metrics_present": any(k in {"l2", "linf"} for row in rows for k in row)}
    if report["prohibited_metrics_present"]: raise RuntimeError("L2/Linf leaked into final results")
    atomic_write_json(root / ("smoke_report.json" if smoke else "evaluation_report.json"), report)
    return report
