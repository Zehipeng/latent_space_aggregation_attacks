from __future__ import annotations

import argparse
import json
from pathlib import Path

from .conditions import expected_output_counts, formal_condition_registry, validate_registry_scale
from .config import load_config
from .preflight import preflight


def guarded_entry(description: str, stage: str) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True)
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    result = preflight(args.config, args.assets_lock, offline=args.offline)
    if args.preflight_only:
        print(json.dumps({"stage": stage, "status": result["status"]}, indent=2)); return
    raise RuntimeError(f"{stage} requires prepared method-specific manifests and GPU assets; preflight passed but execution was not requested through run_formal_batch.py")


def inspect_config_entry() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(); config = load_config(args.config); conditions=formal_condition_registry(); validate_registry_scale(conditions)
    print(json.dumps({"protocol_version": config["protocol_version"], "run_mode": config["run_mode"], "resolved_config_hash": config["resolved_config_hash"], "condition_count": len(conditions), "expected_counts": expected_output_counts(key_count=int(config["key_count"]))}, ensure_ascii=False, indent=2))
