from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.atomic_io import atomic_write_json, atomic_write_text
from ..core.hashing import sha256_file
from ..formal.common import atomic_csv
from .common import plan, verified_record


def finalize(root: Path, settings: dict[str, Any]) -> None:
    conditions, views = plan(settings)
    rows = []
    lookup = {}
    for condition in conditions:
        cid = condition["condition_id"]
        for key in condition["key_ids"]:
            row = verified_record(root / "units" / cid / f"{key}.json", root)
            if not row or row["final_step"] != 150:
                raise RuntimeError(f"Missing or corrupt visual unit: {cid}|{key}")
            rows.append(row)
            lookup[cid, key] = row
    atomic_csv(root / "image_manifest.csv", rows)
    atomic_csv(root / "panel_manifest.csv", [{**view,
        **{f"{name}_path": lookup[view["condition_id"], view["key_id"]][f"{name}_path"]
           for name in ("original", "final")}} for view in views])
    files = sorted(p for p in root.rglob("*") if p.is_file() and
                   (p.suffix == ".png" or p.name in {"image_manifest.csv", "panel_manifest.csv", "run_identity.json"}))
    hashes = {p.relative_to(root).as_posix(): sha256_file(p) for p in files}
    atomic_write_text(root / "checksums.sha256", "".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
    atomic_write_json(root / "visual_report.json", {"status": "VISUAL_COMPLETE", "experiment_version": settings["experiment_version"],
        "formal_statistics": False, "unique_attack_units": len(rows), "panel_rows": len(views),
        "group_keys": settings["group_keys"], "retention": "Original/final PNGs retained; no difference PNGs", "hashes": hashes})
    atomic_write_json(root / "progress.json", {"stage": "complete", "completed_units": len(rows), "total_units": len(views)})
    print(f"VISUAL_COMPLETE: {len(rows)} attacks, {len(views)} panel rows; {root}", flush=True)
