from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from latent_space_aggregation_attacks.core.preflight import preflight

def main() -> None:
    parser=argparse.ArgumentParser(description="Only formal E0-E7 batch orchestrator")
    parser.add_argument("--config",required=True); parser.add_argument("--assets-lock",required=True)
    parser.add_argument("--offline",action="store_true"); parser.add_argument("--preflight-only",action="store_true")
    args=parser.parse_args(); result=preflight(args.config,args.assets_lock,offline=args.offline)
    if args.preflight_only:
        print(json.dumps({"status":result["status"]},indent=2)); return
    raise RuntimeError("Formal execution remains gated until T_formal, assets, and manifests are frozen; then this orchestrator runs 2-key smoke before 200 keys")
if __name__=="__main__": main()
