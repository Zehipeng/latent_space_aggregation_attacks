from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from latent_space_aggregation_attacks.core.manifests import ensure_disjoint, validate_nested_indices

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--spec",required=True); args=parser.parse_args()
    spec=json.loads(Path(args.spec).read_text(encoding="utf-8"))
    ensure_disjoint(spec["pilot_ids"],spec["formal_ids"],"pilot/formal")
    targets=set(spec["forgery_target_ids"]); clean=set(spec["clean_prior_ids"])
    if len(targets)!=200 or len(clean)!=5000 or len(targets & clean)!=200:
        raise ValueError("formal_protocol_v1.9 requires 200 targets contained in the 5000-image val2017 clean pool")
    validate_nested_indices(spec["reference_rows"])
    print(json.dumps({"status":"MANIFESTS_VALID","formal_keys":len(spec["formal_ids"]),"pilot_keys":len(spec["pilot_ids"])},indent=2))
if __name__=="__main__": main()
