from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from latent_space_aggregation_attacks import PROTOCOL_VERSION

from .atomic_io import atomic_write_json, atomic_write_text
from .formal_common import git_sha, read_csv, run_identity
from .gates import SmokeSignature, require_full_run_gate
from .hashing import stable_hash


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _run_worker(
    *, phase: str, config_path: str, assets_lock_path: str, run_dir: Path,
    run_id: str, key_count: int, project_root: Path, smoke: bool,
) -> float:
    command = [
        sys.executable, "-m", "latent_space_aggregation_attacks.core.formal_worker",
        "--phase", phase, "--config", config_path, "--assets-lock", assets_lock_path,
        "--run-dir", str(run_dir), "--run-id", run_id, "--key-count", str(key_count),
        "--project-root", str(project_root), "--offline",
    ]
    if smoke:
        command.append("--smoke")
    environment = dict(os.environ)
    src = str(project_root / "src")
    environment["PYTHONPATH"] = src + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    launch_dir = Path("/root/autodl-tmp/outputs/launch_logs")
    launch_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        launch_dir / f"{run_id}_{'smoke_' if smoke else ''}{phase}.command.txt",
        " ".join(command) + "\n",
    )
    started = time.perf_counter()
    output_log = launch_dir / f"{run_id}_{'smoke_' if smoke else ''}{phase}.log"
    with output_log.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command, cwd=project_root, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            handle.write(line)
            handle.flush()
        return_code = process.wait()
    elapsed = time.perf_counter() - started
    atomic_write_json(
        launch_dir / f"{run_id}_{'smoke_' if smoke else ''}{phase}.exit.json",
        {"phase": phase, "exit_code": return_code, "elapsed_seconds": elapsed,
         "output_log": str(output_log)},
    )
    if return_code != 0:
        raise RuntimeError(f"Formal {phase} worker failed with exit code {return_code}")
    return elapsed


def _signature(identity: dict[str, Any]) -> SmokeSignature:
    return SmokeSignature(
        protocol_version=identity["protocol_version"],
        resolved_config_hash=identity["resolved_config_hash"],
        git_sha=identity["git_sha"],
        assets_lock_hash=identity["assets_lock_hash"],
        sample_manifest_hash=identity["sample_manifest_hash"],
    )


def validate_tree_ring_regression(
    report_path: str | Path, *, config: dict[str, Any], assets_lock: dict[str, Any],
    project_root: str | Path,
) -> dict[str, Any]:
    path = Path(report_path)
    if not path.is_file():
        raise FileNotFoundError(f"Tree-Ring regression report is required: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "PASSED", "protocol_version": PROTOCOL_VERSION,
        "git_sha": git_sha(project_root),
        "source_resolved_config_hash": config["resolved_config_hash"],
        "assets_lock_hash": stable_hash(assets_lock),
    }
    mismatches = {key: (report.get(key), value) for key, value in expected.items() if report.get(key) != value}
    if mismatches:
        raise RuntimeError(f"Tree-Ring regression report does not match this formal run: {mismatches}")
    return report


def validate_batch_equivalence(
    report_path: str | Path, *, config: dict[str, Any], assets_lock: dict[str, Any],
    project_root: str | Path,
) -> dict[str, Any]:
    path = Path(report_path)
    if not path.is_file():
        raise FileNotFoundError(f"Batch equivalence report is required: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "PASSED", "protocol_version": PROTOCOL_VERSION,
        "git_sha": git_sha(project_root),
        "source_resolved_config_hash": config["resolved_config_hash"],
        "assets_lock_hash": stable_hash(assets_lock),
        "validated_batching": config["validated_batching"],
    }
    mismatches = {key: (report.get(key), value) for key, value in expected.items() if report.get(key) != value}
    if mismatches:
        raise RuntimeError(f"Batch equivalence report does not match this formal run: {mismatches}")
    if report.get("failures"):
        raise RuntimeError(f"Batch equivalence report contains failures: {report['failures']}")
    return report


def _read_manifest_identity(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    recorded = value.pop("manifest_hash", None)
    if recorded != stable_hash(value):
        raise ValueError("Smoke run manifest is corrupt")
    return value


def _eta_report(smoke_dir: Path, timings: dict[str, float], output: Path) -> dict[str, Any]:
    attack_rows = read_csv(smoke_dir / "manifests/attack_outputs.csv")
    iterative = [float(row["optimization_compute_time"]) for row in attack_rows if int(row["final_step"]) > 0]
    scale = 100.0
    p50_unit = statistics.median(iterative) if iterative else 0.0
    # Scaling the complete attack wall time retains proxy encoding, checkpoint
    # I/O, E7 construction and model-load overhead omitted from optimizer-only rows.
    p50_attack = timings["attack"] * scale
    p90_unit = sorted(iterative)[max(0, math.ceil(0.9 * len(iterative)) - 1)] if iterative else 0.0
    p90_attack = p50_attack + max(0.0, p90_unit - p50_unit) * len(iterative) * scale
    fixed_scaled = (timings["prepare"] + timings["evaluate"]) * scale
    cleanup_report = smoke_dir / "logs/spool_cleanup.json"
    if cleanup_report.is_file():
        spool_bytes = int(json.loads(cleanup_report.read_text(encoding="utf-8"))["removed_bytes"])
    else:
        spool_bytes = _tree_bytes(smoke_dir / "evaluation_spool") + _tree_bytes(smoke_dir / "curve_checkpoint_spool")
    phase_runtime = {
        phase: json.loads((smoke_dir / f"logs/{phase}_runtime.json").read_text(encoding="utf-8"))
        for phase in ("prepare", "attack", "evaluate")
    }
    p50_seconds = fixed_scaled + p50_attack
    p90_seconds = fixed_scaled + p90_attack
    generated_at = datetime.now(timezone.utc)
    full_primary_outputs = 13_200
    full_e7_outputs = 13_200
    full_trajectory_rows = 21_600
    report = {
        "status": "ESTIMATED_AWAITING_FULL_RUN_APPROVAL",
        "protocol_version": PROTOCOL_VERSION,
        "source": "same-config 2-key smoke on the active GPU",
        "generated_at_utc": generated_at.isoformat(),
        "hardware_software": {
            "gpu_name": phase_runtime["attack"]["gpu_name"],
            "torch_version": phase_runtime["attack"]["torch_version"],
            "torch_cuda_version": phase_runtime["attack"]["torch_cuda_version"],
            "python_version": phase_runtime["attack"]["python_version"],
            "parallel_workers": 1,
            "attack_batch_size": 4,
            "inversion_batch_size": 8,
        },
        "stage_measurements": phase_runtime,
        "formal_stage_counts": {
            "reference_key_model_watermark_groups": 1_200,
            "primary_attack_outputs": full_primary_outputs,
            "e7_control_outputs": full_e7_outputs,
            "final_and_wrong_key_evaluation_outputs": full_primary_outputs + full_e7_outputs,
            "detector_trajectory_rows": full_trajectory_rows,
            "completed_formal_outputs": 0,
            "remaining_formal_outputs": full_primary_outputs + full_e7_outputs,
        },
        "serial_p50_seconds": p50_seconds,
        "actual_parallel_p50_seconds": p50_seconds,
        "p50_seconds": p50_seconds,
        "p90_seconds": p90_seconds,
        "estimated_completion_p50_utc": (generated_at + timedelta(seconds=p50_seconds)).isoformat(),
        "estimated_completion_p90_utc": (generated_at + timedelta(seconds=p90_seconds)).isoformat(),
        "estimated_peak_spool_bytes": int(spool_bytes * scale),
        "smoke_phase_seconds": timings,
        "notes": [
            "ETA is hardware-dependent and is not a completion promise.",
            "The estimate includes preparation, attack, final/wrong-key evaluation, trajectory I/O and plotting.",
            "Preparation and evaluation are conservatively scaled from their complete 2-key phase wall times.",
            "Attack P50/P90 use the per-unit compute times recorded across every smoke method and condition.",
            "Full execution requires an explicit --approve-full-run flag.",
        ],
    }
    atomic_write_json(output, report)
    return report


def _recorded_smoke_timings(output_root: Path, run_id: str) -> dict[str, float]:
    result = {}
    for phase in ("prepare", "attack", "evaluate"):
        path = output_root / "launch_logs" / f"{run_id}_smoke_{phase}.exit.json"
        if not path.is_file():
            raise FileNotFoundError(f"Missing smoke timing record: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload["exit_code"]) != 0:
            raise RuntimeError(f"Smoke timing record contains a failed phase: {phase}")
        result[phase] = float(payload["elapsed_seconds"])
    return result


def run_formal_forgery_batch(
    *, config: dict[str, Any], assets_lock: dict[str, Any], config_path: str,
    smoke_config_path: str, assets_lock_path: str, run_id: str, project_root: str | Path,
    regression_report_path: str, batch_equivalence_report_path: str,
    smoke_only: bool, approve_full_run: bool,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    validate_tree_ring_regression(
        regression_report_path, config=config, assets_lock=assets_lock, project_root=project,
    )
    validate_batch_equivalence(
        batch_equivalence_report_path, config=config, assets_lock=assets_lock, project_root=project,
    )
    output_root = Path(config["output_root"])
    smoke_dir = output_root / "smoke/formal_forgery" / f"{run_id}_smoke"
    full_dir = output_root / "formal_forgery" / run_id
    smoke_timings: dict[str, float] = {}
    smoke_report_path = smoke_dir / "smoke_report.json"
    smoke_was_reviewable_at_start = (
        smoke_report_path.is_file() and (smoke_dir / "runtime_estimate.json").is_file()
    )
    if not smoke_report_path.is_file():
        for phase in ("prepare", "attack", "evaluate"):
            smoke_timings[phase] = _run_worker(
                phase=phase, config_path=smoke_config_path, assets_lock_path=assets_lock_path,
                run_dir=smoke_dir, run_id=run_id, key_count=2, project_root=project, smoke=True,
            )
        _eta_report(smoke_dir, smoke_timings, smoke_dir / "runtime_estimate.json")
    elif not (smoke_dir / "runtime_estimate.json").is_file():
        _eta_report(
            smoke_dir, _recorded_smoke_timings(output_root, run_id),
            smoke_dir / "runtime_estimate.json",
        )
    smoke_report = json.loads(smoke_report_path.read_text(encoding="utf-8"))
    smoke_identity = _read_manifest_identity(smoke_dir / "manifests/run_manifest.json")
    full_identity = run_identity(
        config=config, assets_lock=assets_lock, project_root=project, run_id=run_id,
        key_ids=[f"key_{index:03d}" for index in range(200)], task="forgery",
    )
    require_full_run_gate(
        _signature(full_identity), _signature(smoke_identity), smoke_report.get("status") == "PASSED",
    )
    result: dict[str, Any] = {
        "status": "SMOKE_PASSED", "smoke_dir": str(smoke_dir),
        "runtime_estimate": str(smoke_dir / "runtime_estimate.json"),
    }
    # A command that has just generated the ETA cannot also count as approval
    # of that unseen report.  Full execution therefore requires a later,
    # explicit invocation with --approve-full-run.
    if smoke_only or not approve_full_run or not smoke_was_reviewable_at_start:
        return result
    for phase in ("prepare", "attack", "evaluate"):
        _run_worker(
            phase=phase, config_path=config_path, assets_lock_path=assets_lock_path,
            run_dir=full_dir, run_id=run_id, key_count=200, project_root=project, smoke=False,
        )
    result.update(status="FORMAL_FORGERY_COMPLETE", run_dir=str(full_dir))
    return result
