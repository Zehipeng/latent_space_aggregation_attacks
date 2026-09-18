"""RingID/FR-LA diagnostics, with physically separate prepare/attack processes."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.hashing import stable_hash
from latent_space_aggregation_attacks.core.locking import UnitLock
from latent_space_aggregation_attacks.core.preflight import preflight
from latent_space_aggregation_attacks.formal.common import git_sha
from latent_space_aggregation_attacks.visual.common import load_settings, plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default=str(PROJECT / "configs/visual/ringid_fr_la_v3.yaml"))
    parser.add_argument("--config", default=str(PROJECT / "configs/current/formal_v1p22.yaml"))
    parser.add_argument("--assets-lock", default=str(PROJECT / "local_assets/assets.lock.json"))
    parser.add_argument("--run-id", default="ringid_fr_la_visual_v3_20260918")
    parser.add_argument("--phase", choices=["run", "preflight", "prepare", "attack", "finalize"], default="run")
    parser.add_argument("--dry-run", action="store_true", help="Print approved matrix without reading assets or loading models")
    args = parser.parse_args()
    settings = load_settings(args.settings)
    conditions, views = plan(settings)
    if args.dry_run:
        print(json.dumps({"settings": settings, "unique_conditions": conditions,
                          "attack_units": len(conditions)*2, "panel_rows": len(views)}, indent=2))
        return
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", args.run_id):
        parser.error("run-id must be a simple directory name")
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"
    checked = preflight(args.config, args.assets_lock, offline=True)
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=PROJECT).returncode:
        raise RuntimeError("Tracked source changes present; run the exact pushed commit")
    config, assets = checked["config"], checked["assets"]
    root = Path(config["output_root"]) / "visual_ablation" / args.run_id
    # Separate groups need 250 references, 40 output PNGs and 30 resume states.
    free = shutil.disk_usage(Path(config["output_root"]).parent).free
    if free < 5 * 1024**3: raise RuntimeError("Visual run requires at least 5 GiB free disk")
    identity = {"experiment_version": settings["experiment_version"], "formal_statistics": False,
        "run_id": args.run_id, "git_sha": git_sha(PROJECT), "settings": settings,
        "source_config_hash": config["resolved_config_hash"], "assets_lock_hash": stable_hash(assets)}
    if args.phase == "preflight":
        print(json.dumps({"status": "VISUAL_PREFLIGHT_PASSED", "identity": identity,
                          "attack_units": len(views), "minimum_free_bytes": 5*1024**3, "free_bytes": free}, indent=2))
        return
    root.mkdir(parents=True, exist_ok=True)
    identity_path = root / "run_identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text(encoding="utf-8")) != identity:
            raise RuntimeError("Run identity changed; use a new run-id")
    else:
        atomic_write_json(identity_path, identity)
    if args.phase == "run":
        with UnitLock(root / "workflow.lock"):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            atomic_write_json(root / "executions" / f"{stamp}.json", {"argv": sys.argv, "python": sys.version,
                "git_sha": identity["git_sha"], "started_at_utc": stamp})
            for phase in ("prepare", "attack", "finalize"):
                command = [sys.executable, "-u", str(Path(__file__).resolve()),
                    "--settings", str(Path(args.settings).resolve()), "--config", str(Path(args.config).resolve()),
                    "--assets-lock", str(Path(args.assets_lock).resolve()), "--run-id", args.run_id, "--phase", phase]
                subprocess.run(command, check=True, cwd=PROJECT)
        return
    with UnitLock(root / "phase.lock"):
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        runtime = {"phase": args.phase, "started_at_utc": started_at, "argv": sys.argv,
                   "python": sys.version, "git_sha": identity["git_sha"]}
        try:
            if args.phase == "prepare":
                from latent_space_aggregation_attacks.visual.prepare import prepare
                prepare(config, assets, root, args.run_id, PROJECT, settings)
            elif args.phase == "attack":
                from latent_space_aggregation_attacks.visual.attack import attack
                attack(assets, root, identity, settings)
            else:
                from latent_space_aggregation_attacks.visual.report import finalize
                finalize(root, settings)
            runtime.update(status="COMPLETE", exit_code=0)
        except BaseException as exc:
            runtime.update(status="FAILED", exit_code=1, error=repr(exc))
            raise
        finally:
            runtime.update(ended_at_utc=datetime.now(timezone.utc).isoformat(),
                           elapsed_seconds=time.perf_counter()-started)
            runtime["packages"] = {}
            for package in ("torch", "torchvision", "diffusers", "transformers", "numpy", "Pillow"):
                try: runtime["packages"][package] = version(package)
                except PackageNotFoundError: runtime["packages"][package] = "unavailable"
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available():
                runtime.update(gpu=torch.cuda.get_device_name(0), cuda=torch.version.cuda,
                               gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated())
            atomic_write_json(root / "logs" / f"{args.phase}_runtime.json", runtime)


if __name__ == "__main__":
    main()
