from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.reviewer_selection_mechanism.reuse import (
    reuse_candidate_bank,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify and reuse the first 50 keys of an E2/E4 candidate bank",
    )
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--destination-run", required=True)
    parser.add_argument("--destination-run-id", required=True)
    parser.add_argument("--key-count", type=int, default=50)
    parser.add_argument(
        "--copy", action="store_true",
        help="copy images instead of creating same-filesystem hard links",
    )
    args = parser.parse_args()
    result = reuse_candidate_bank(
        source_run=args.source_run,
        destination_run=args.destination_run,
        destination_run_id=args.destination_run_id,
        key_count=args.key_count,
        copy=args.copy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
