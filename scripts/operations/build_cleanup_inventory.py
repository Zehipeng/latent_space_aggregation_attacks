from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> None:
    p=argparse.ArgumentParser(description="Dry-run only; never deletes files"); p.add_argument("--root",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    root=Path(a.root).resolve(); records=[]
    for path in root.rglob("*"):
        if path.is_file() and any(part in {"resume_state","evaluation_spool","curve_checkpoint_spool"} for part in path.parts):
            records.append({"path":str(path),"size_bytes":path.stat().st_size,"category":"protocol_temporary","reason":"candidate only after protocol verification"})
    Path(a.output).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"dry-run inventory only: {len(records)} files")
if __name__=="__main__": main()
