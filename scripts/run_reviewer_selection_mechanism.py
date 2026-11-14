from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.models.asset_lock import (
    load_and_verify_assets, require_offline, validate_formal_assets,
)
from latent_space_aggregation_attacks.reviewer_selection_mechanism.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reviewer-response E2 reference-selection and E4 mechanism experiment",
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--smoke-config")
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--tree-ring-regression-report")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--approve-full-run", action="store_true")
    args = parser.parse_args()
    require_offline(args.offline)
    config = load_config(args.config)
    lock = load_and_verify_assets(args.assets_lock)
    assets = validate_formal_assets(lock)
    if args.preflight_only:
        print(json.dumps({
            "status": "PREFLIGHT_PASSED",
            "protocol_version": config["protocol_version"],
            "verified_assets": sorted(assets), "asset_count": len(assets),
            "condition_count": 48,
            "expected_smoke_outputs": 96,
            "expected_formal_outputs": 9600,
        }, indent=2))
        return
    for name in ("smoke_config", "run_id", "tree_ring_regression_report"):
        if not getattr(args, name):
            parser.error(f"--{name.replace('_', '-')} is required")
    from latent_space_aggregation_attacks.reviewer_selection_mechanism.orchestrator import run
    result = run(
        config_path=args.config, smoke_config_path=args.smoke_config,
        lock_path=args.assets_lock, run_id=args.run_id,
        regression_report=args.tree_ring_regression_report,
        project=PROJECT_ROOT, smoke_only=args.smoke_only,
        approve_full_run=args.approve_full_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
