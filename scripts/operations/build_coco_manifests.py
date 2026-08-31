from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.data.coco import load_val_images, materialize_manifests, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build formal_protocol_v1.10 val2017 role manifests")
    parser.add_argument("--val-dir", required=True)
    parser.add_argument("--instances", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    manifests = materialize_manifests(load_val_images(args.instances), args.val_dir)
    summary = {}
    for name, rows in manifests.items():
        destination = output / name
        write_csv(destination, rows)
        summary[name] = {"rows": len(rows), "sha256": sha256_file(destination)}
    formal_targets = {row["image_id"] for row in manifests["formal_forgery_target_manifest.csv"]}
    formal_clean = {row["image_id"] for row in manifests["formal_clean_prior_manifest.csv"]}
    pilot_targets = {row["image_id"] for row in manifests["p0_forgery_target_manifest.csv"]}
    if len(formal_targets) != 200 or len(formal_clean) != 5000 or len(formal_targets & formal_clean) != 200:
        raise RuntimeError("formal_protocol_v1.10 data role audit failed")
    if formal_targets & pilot_targets:
        raise RuntimeError("P0/formal forgery targets overlap")
    print(json.dumps({"status": "COCO_MANIFESTS_VALID", "manifests": summary}, indent=2))


if __name__ == "__main__":
    main()
