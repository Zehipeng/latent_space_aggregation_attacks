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

from ..core.atomic_io import atomic_write_json, atomic_write_text
from ..core.gates import SmokeSignature, require_full_run_gate
from ..core.hashing import stable_hash
from ..formal.common import read_csv
from . import PROTOCOL_VERSION
from .common import git_sha, identity, keys
from .config import compatibility_hash, load_config


def _worker(phase: str, config_path: str, lock_path: str, root: Path,
            run_id: str, project: Path, output_root: Path, smoke: bool) -> float:
    command = [sys.executable, "-m", "latent_space_aggregation_attacks.limited_access.worker",
               "--phase", phase, "--config", config_path, "--assets-lock", lock_path,
               "--run-dir", str(root), "--run-id", run_id,
               "--project-root", str(project), "--offline"]
    launch = output_root / "launch_logs"; launch.mkdir(parents=True, exist_ok=True)
    prefix = f"{run_id}_{'smoke_' if smoke else ''}{phase}"
    atomic_write_text(launch / f"{prefix}.command.txt", " ".join(command) + "\n")
    env = dict(os.environ); env["PYTHONPATH"] = str(project / "src") + os.pathsep + env.get("PYTHONPATH", "")
    started = time.perf_counter()
    with (launch / f"{prefix}.log").open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(command, cwd=project, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True); handle.write(line); handle.flush()
        code = process.wait()
    elapsed = time.perf_counter() - started
    atomic_write_json(launch / f"{prefix}.exit.json", {"phase": phase, "exit_code": code,
                       "elapsed_seconds": elapsed})
    if code: raise RuntimeError(f"limited-access {phase} failed with exit code {code}")
    return elapsed


def _signature(value: dict[str, Any]) -> SmokeSignature:
    return SmokeSignature(value["protocol_version"], value["resolved_config_hash"], value["git_sha"],
                          value["assets_lock_hash"], value["sample_manifest_hash"])


def _read_identity(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8")); digest = value.pop("manifest_hash", None)
    if digest != stable_hash(value): raise RuntimeError("smoke identity is corrupt")
    return value


def _validate_regression(path: str | Path, config: dict[str, Any], lock: dict[str, Any], project: Path) -> None:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"status": "PASSED", "protocol_version": PROTOCOL_VERSION,
                "git_sha": git_sha(project), "source_resolved_config_hash": config["resolved_config_hash"],
                "assets_lock_hash": stable_hash(lock)}
    wrong = {k: (report.get(k), v) for k, v in expected.items() if report.get(k) != v}
    if wrong: raise RuntimeError(f"Tree-Ring regression report mismatch: {wrong}")


def _report(smoke_dir: Path, timings: dict[str, float]) -> dict[str, Any]:
    rows = read_csv(smoke_dir / "manifests/attack_outputs.csv")
    units = sorted(float(row["optimization_compute_time"]) for row in rows)
    p50 = statistics.median(units); p90 = units[max(0, math.ceil(.9*len(units))-1)]
    prep = json.loads((smoke_dir / "preparation_report.json").read_text(encoding="utf-8"))
    attack = json.loads((smoke_dir / "attack_report.json").read_text(encoding="utf-8"))
    cleanup = json.loads((smoke_dir / "logs/png_cleanup.json").read_text(encoding="utf-8"))
    persistent = sum(path.stat().st_size for path in smoke_dir.rglob("*") if path.is_file())
    scale = 100; fixed = (timings["prepare"] + timings["evaluate"]) * scale
    p50_total = fixed + p50 * 1200; p90_total = fixed + p90 * 1200
    now = datetime.now(timezone.utc)
    report = {"status": "ESTIMATED_AWAITING_FULL_RUN_APPROVAL", "source": "same-config 2-key smoke",
              "protocol_version": PROTOCOL_VERSION, "generated_at_utc": now.isoformat(),
              "smoke_output_count": len(rows), "formal_output_count": 1200,
              "unit_p50_seconds": p50, "unit_p90_seconds": p90,
              "p50_seconds": p50_total, "p90_seconds": p90_total,
              "estimated_completion_p50_utc": (now+timedelta(seconds=p50_total)).isoformat(),
              "estimated_completion_p90_utc": (now+timedelta(seconds=p90_total)).isoformat(),
              "gpu_name": attack["gpu_name"], "gpu_peak_reserved_bytes": attack["gpu_peak_reserved_bytes"],
              "smoke_phase_seconds": timings,
              "smoke_disk_peak_observed_or_reconstructed_bytes": persistent + int(cleanup["removed_bytes"]),
              "estimated_formal_disk_peak_bytes": (persistent + int(cleanup["removed_bytes"])) * scale,
              "notes": ["Includes preparation, 1200 fixed-budget attacks, detection, quality metrics and FID.",
                        "Low ASR does not stop progression between watermarks.",
                        "A later explicit --approve-full-run invocation is required."]}
    atomic_write_json(smoke_dir / "runtime_estimate.json", report); return report


def run(*, config_path: str, smoke_config_path: str, lock_path: str, run_id: str,
        regression_report: str, project: Path, smoke_only: bool,
        approve_full_run: bool) -> dict[str, Any]:
    from ..models.asset_lock import load_and_verify_assets, validate_formal_assets
    config, smoke_config = load_config(config_path), load_config(smoke_config_path)
    if compatibility_hash(config) != compatibility_hash(smoke_config):
        raise RuntimeError("smoke and formal configs are not compatible")
    lock = load_and_verify_assets(lock_path); validate_formal_assets(lock)
    _validate_regression(regression_report, config, lock, project)
    output_root = Path(config["output_root"]); smoke_dir = output_root / "smoke/limited_access" / f"{run_id}_smoke"
    full_dir = output_root / "limited_access" / run_id
    report_path = smoke_dir / "smoke_report.json"; reviewable = report_path.is_file() and (smoke_dir / "runtime_estimate.json").is_file()
    timings: dict[str, float] = {}
    if not report_path.is_file():
        for phase in ("prepare", "attack", "evaluate"):
            timings[phase] = _worker(phase, smoke_config_path, lock_path, smoke_dir, run_id, project, output_root, True)
        _report(smoke_dir, timings)
    smoke_report = json.loads(report_path.read_text(encoding="utf-8"))
    smoke_identity = _read_identity(smoke_dir / "manifests/run_manifest.json")
    full_identity = identity(config, lock, project, run_id, keys(200))
    require_full_run_gate(_signature(full_identity), _signature(smoke_identity), smoke_report["status"] == "PASSED")
    result = {"status": "SMOKE_PASSED", "smoke_dir": str(smoke_dir),
              "runtime_estimate": str(smoke_dir / "runtime_estimate.json")}
    if smoke_only or not approve_full_run or not reviewable: return result
    for phase in ("prepare", "attack", "evaluate"):
        _worker(phase, config_path, lock_path, full_dir, run_id, project, output_root, False)
    result.update(status="FORMAL_COMPLETE", run_dir=str(full_dir)); return result
