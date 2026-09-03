from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED_STAGES={"asset_load","reference_generation","reference_encoding","jain_forgery","proposed_forgery","jain_removal","proposed_removal","simple_averaging","distortions","final_detection","final_quality"}
def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--measurements",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    rows=json.loads(Path(a.measurements).read_text(encoding="utf-8")); observed={r["stage"] for r in rows}
    missing=sorted(REQUIRED_STAGES-observed)
    if missing: raise ValueError(f"Missing ETA stages: {missing}")
    result={"status":"ESTIMATED","measurements":rows,"note":"P50/P90 are hardware-dependent and not completion promises"}
    Path(a.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
if __name__=="__main__": main()
