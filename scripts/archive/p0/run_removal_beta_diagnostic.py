import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from latent_space_aggregation_attacks.archive.p0_runtime import run_removal_diagnostic
from latent_space_aggregation_attacks.core.preflight import preflight


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the fixed-budget 10-key cross-model removal diagnostic at beta=1.5"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--output-root", default="../outputs")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    checked = preflight(args.config, args.assets_lock, offline=args.offline)
    if args.preflight_only:
        print(json.dumps({"stage": "removal_beta_1p5_diagnostic", "status": checked["status"]}, indent=2))
        return
    run_id = args.run_id or datetime.now(timezone.utc).strftime("removal_beta15_%Y%m%dT%H%M%SZ")
    result = run_removal_diagnostic(
        config=checked["config"], assets_lock=checked["assets"], output_root=args.output_root,
        run_id=run_id, smoke_only=args.smoke_only,
        project_root=Path(__file__).resolve().parents[2],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
