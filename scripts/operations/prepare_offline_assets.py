from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.hashing import sha256_tree

def main() -> None:
    parser=argparse.ArgumentParser(description="Create assets.lock.json from explicitly prepared local assets")
    parser.add_argument("--inventory",required=True,help="JSON list of name/kind/path/revision/sha256 records")
    parser.add_argument("--output",required=True); parser.add_argument("--allow-network",action="store_true")
    args=parser.parse_args()
    if args.allow_network:
        raise RuntimeError("Downloads require a separately reviewed asset-preparation command; this tool only locks existing files")
    specifications=json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    if not isinstance(specifications,list): raise ValueError("Inventory must be a JSON list")
    assets=[]
    for spec in specifications:
        local_path=Path(spec["path"]).resolve(); digest,size,count=sha256_tree(local_path)
        if spec.get("kind") in {"model","watermark_code"} and not spec.get("revision"):
            raise ValueError(f"Revision is required for {spec['name']}")
        assets.append({**spec,"path":str(local_path),"sha256":digest,"size_bytes":size,"file_count":count})
    atomic_write_json(args.output,{"schema_version":1,"assets":assets})
if __name__=="__main__": main()
