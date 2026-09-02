from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from ..core.atomic_io import atomic_write_json
from ..core.preflight import preflight


def main() -> None:
    parser = argparse.ArgumentParser(description="Physically isolated formal forgery stage worker")
    parser.add_argument("--phase", choices=("prepare", "attack", "evaluate"), required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--key-count", type=int, choices=(2, 200), required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--offline", action="store_true", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    checked = preflight(args.config, args.assets_lock, offline=args.offline)
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("Formal worker requires a CUDA GPU")
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    key_ids = [f"key_{index:03d}" for index in range(args.key_count)]
    common = {
        "config": checked["config"], "assets_lock": checked["assets"],
        "run_dir": Path(args.run_dir), "run_id": args.run_id, "key_ids": key_ids,
    }
    if args.phase == "prepare":
        from .prepare import prepare_formal_forgery
        result = prepare_formal_forgery(**common, project_root=args.project_root)
    elif args.phase == "attack":
        # Importing only this branch is the process-level detector isolation boundary.
        from .attack import run_formal_forgery_attack
        result = run_formal_forgery_attack(**common, project_root=args.project_root)
    else:
        from .evaluate import evaluate_formal_forgery
        result = evaluate_formal_forgery(**common, smoke=args.smoke)
    elapsed = time.perf_counter() - started
    runtime = {
        "phase": args.phase, "elapsed_seconds": elapsed,
        "gpu_peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "gpu_peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "gpu_name": torch.cuda.get_device_name(0), "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda, "python_version": platform.python_version(),
        "key_count": args.key_count, "smoke": args.smoke,
    }
    atomic_write_json(Path(args.run_dir) / f"logs/{args.phase}_runtime.json", runtime)
    result["worker_runtime"] = runtime
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
