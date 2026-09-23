"""Independent 40-key detector trajectories, with detector-free attack subprocesses."""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.hashing import stable_hash, sha256_file
from latent_space_aggregation_attacks.core.locking import UnitLock
from latent_space_aggregation_attacks.trajectory.common import (
    load_settings, MODEL, configured_tasks, checkpoint_steps, units,
)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settings", default=str(PROJECT / "configs/diagnostics/single_img_vs_fr_la_trajectory_v1.yaml"))
    p.add_argument("--config", default=str(PROJECT / "configs/current/formal_v1p22.yaml"))
    p.add_argument("--assets-lock", default=str(PROJECT / "local_assets/assets.lock.json"))
    p.add_argument("--run-id", default="single_img_fr_la_40key_trajectory_v1_mean40_20260918")
    p.add_argument("--phase", choices=["run", "preflight", "prepare", "attack", "evaluate", "finalize"], default="run")
    p.add_argument("--task", choices=["forgery", "removal"])
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    settings = load_settings(a.settings)
    tasks = configured_tasks(settings)
    if a.dry_run:
        attack_units = sum(len(units(task, settings)) for task in tasks)
        print(json.dumps({"settings": settings, "attack_units": attack_units,
            "records": attack_units * len(checkpoint_steps(settings)),
            "checkpoint_steps": list(checkpoint_steps(settings)), "formal_statistics": False}, indent=2))
        return
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", a.run_id):
        p.error("Invalid run-id")
    if a.phase in ("attack", "evaluate") and not a.task:
        p.error("--task is required")
    if a.task and a.task not in tasks:
        p.error(f"Task {a.task!r} is not approved by settings; expected one of {tasks}")
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=PROJECT).returncode:
        raise RuntimeError("Tracked source must be clean and match the pushed commit")
    from latent_space_aggregation_attacks.core.preflight import preflight
    from latent_space_aggregation_attacks.formal.common import git_sha, assets_by_name, model_config, adapter_config
    checked = preflight(a.config, a.assets_lock, offline=True)
    config, assets = checked["config"], checked["assets"]
    output = Path(config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output).free < 10 * 1024**3:
        raise RuntimeError("At least 10 GiB free space required")
    root = output / "detector_trajectory" / a.run_id
    root.mkdir(parents=True, exist_ok=True)
    identity = {"version": settings["experiment_version"], "run_id": a.run_id, "settings": settings,
        "git_sha": git_sha(PROJECT), "config_hash": config["resolved_config_hash"],
        "assets_hash": stable_hash(assets), "formal_statistics": False}
    ip = root / "run_identity.json"
    if ip.exists() and json.loads(ip.read_text(encoding="utf-8")) != identity:
        raise RuntimeError("Identity changed; use a new run-id")
    atomic_write_json(ip, identity)
    base = [sys.executable, "-u", str(Path(__file__).resolve()), "--settings", str(Path(a.settings).resolve()),
        "--config", str(Path(a.config).resolve()), "--assets-lock", str(Path(a.assets_lock).resolve()), "--run-id", a.run_id]
    if a.phase == "run":
        with UnitLock(root / "workflow.lock"):
            phases = [("preflight", None), ("prepare", None)]
            selected_tasks = [a.task] if a.task else list(tasks)
            for task in selected_tasks:
                phases += [("attack", task), ("evaluate", task)]
            phases.append(("finalize", a.task))
            for phase, task in phases:
                subprocess.run(base + ["--phase", phase] + (["--task", task] if task else []), check=True, cwd=PROJECT)
        return
    with UnitLock(root / "phase.lock"):
        status = {"phase": a.phase, "task": a.task, "argv": sys.argv, "python": sys.version,
                  "started": datetime.now(timezone.utc).isoformat()}
        try:
            if a.phase == "preflight":
                import torch
                from latent_space_aggregation_attacks.models.loaders import load_proxy_vae, load_target_pipeline
                from latent_space_aggregation_attacks.watermarks.base import registered_adapter
                from latent_space_aggregation_attacks.core.seeds import derive_seed
                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA GPU required")
                amap = assets_by_name(assets)
                vae = load_proxy_vae(model_config(amap, MODEL), offline=True)
                del vae
                torch.cuda.empty_cache()
                pipe = load_target_pipeline(model_config(amap, MODEL), offline=True)
                for wm in settings["watermarks"]:
                    adapter = registered_adapter(wm, adapter_config(config, wm, pipe, amap))
                    for i in range(40):
                        key = adapter.create_key({"watermark_seed": derive_seed("watermark_key", wm, f"key_{i:03d}")})
                        del key
                status.update(status="ASSETS_READY", gpu=torch.cuda.get_device_name(0))
                print(json.dumps(status, indent=2))
            elif a.phase == "prepare":
                from latent_space_aggregation_attacks.formal.prepare import prepare_formal_removal
                selected = copy.deepcopy(config)
                selected.update(model_settings=[MODEL], watermarks=settings["watermarks"])
                selected["resolved_config_hash"] = stable_hash({k:v for k,v in selected.items() if k != "resolved_config_hash"})
                prepare_formal_removal(config=selected, assets_lock=assets, run_dir=root / "shared_preparation",
                    run_id=a.run_id, key_ids=[f"key_{i:03d}" for i in range(40)], project_root=PROJECT)
            elif a.phase == "attack":
                from latent_space_aggregation_attacks.trajectory.attack import attack
                attack(assets, root, identity, a.task)
            elif a.phase == "evaluate":
                from latent_space_aggregation_attacks.trajectory.evaluate import evaluate
                evaluate(config, assets, root, identity, a.task)
            else:
                reports = []
                selected_tasks = [a.task] if a.task else list(tasks)
                expected_rows = len(units(selected_tasks[0], settings)) * len(checkpoint_steps(settings))
                for task in selected_tasks:
                    d = root / "evaluation" / task
                    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
                    if report["status"] != "COMPLETE" or report["rows"] != expected_rows:
                        raise RuntimeError("Incomplete trajectory evaluation")
                    if sha256_file(d / "per_key_trajectory.csv") != report["per_key_sha256"] or sha256_file(d / "trajectory_summary.csv") != report["summary_sha256"]:
                        raise RuntimeError("Evaluation hash mismatch")
                    reports.append(report)
                atomic_write_json(root / "final_report.json", {"status": "COMPLETE", "identity": identity, "tasks": reports})
            status.update(exit_code=0)
        except BaseException as exc:
            status.update(exit_code=1, error=repr(exc))
            raise
        finally:
            status["ended"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(root / "logs" / f"{a.phase}_{a.task or 'shared'}_runtime.json", status)

if __name__ == "__main__":
    main()
