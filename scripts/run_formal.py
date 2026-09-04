from __future__ import annotations
import argparse, json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from latent_space_aggregation_attacks.core.preflight import preflight
from latent_space_aggregation_attacks.formal.orchestrator import run_formal_forgery, run_formal_removal

def main() -> None:
    parser=argparse.ArgumentParser(description="Protocol-locked scalar formal orchestrator")
    parser.add_argument("--config",required=True); parser.add_argument("--assets-lock",required=True)
    parser.add_argument("--offline",action="store_true"); parser.add_argument("--preflight-only",action="store_true")
    parser.add_argument("--task", choices=("forgery", "removal"), default="forgery")
    parser.add_argument("--smoke-config")
    parser.add_argument("--tree-ring-regression-report")
    parser.add_argument("--run-id")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--approve-full-run", action="store_true")
    args=parser.parse_args(); result=preflight(args.config,args.assets_lock,offline=args.offline)
    if args.preflight_only:
        print(json.dumps({"status":result["status"]},indent=2)); return
    if not args.run_id:
        parser.error("--run-id is required unless --preflight-only is used")
    if not args.smoke_config:
        parser.error("--smoke-config is required unless --preflight-only is used")
    if not args.tree_ring_regression_report:
        parser.error("--tree-ring-regression-report is required unless --preflight-only is used")
    smoke = preflight(args.smoke_config, args.assets_lock, offline=args.offline)
    if smoke["config"]["run_mode"] != "smoke" or int(smoke["config"]["key_count"]) != 2:
        parser.error("--smoke-config must be the protocol-locked 2-key smoke configuration")
    orchestrate = run_formal_forgery if args.task == "forgery" else run_formal_removal
    value = orchestrate(
        config=result["config"], assets_lock=result["assets"], config_path=args.config,
        smoke_config_path=args.smoke_config, assets_lock_path=args.assets_lock, run_id=args.run_id,
        regression_report_path=args.tree_ring_regression_report,
        project_root=PROJECT_ROOT, smoke_only=args.smoke_only,
        approve_full_run=args.approve_full_run,
    )
    print(json.dumps(value, ensure_ascii=False, indent=2))
if __name__=="__main__": main()
