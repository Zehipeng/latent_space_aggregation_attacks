from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.data.prompts import (
    build_prompt_rows,
    read_parquet_prompts,
    write_prompt_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build disjoint formal/P0 prompt banks from the locked train parquet")
    parser.add_argument("--train-parquet", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    actual = sha256_file(args.train_parquet)
    if actual != args.expected_sha256:
        raise ValueError(f"Prompt parquet SHA-256 mismatch: {actual}")
    prompts = read_parquet_prompts(args.train_parquet)
    rows = build_prompt_rows(prompts)
    write_prompt_manifest(args.output, rows)
    print(json.dumps({
        "status": "PROMPT_MANIFEST_WRITTEN",
        "source_rows": len(prompts),
        "manifest_rows": len(rows),
        "pilot_rows": 2_500,
        "formal_rows": 5_000,
        "manifest_sha256": sha256_file(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
