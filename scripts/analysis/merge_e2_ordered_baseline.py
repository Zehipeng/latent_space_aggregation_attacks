from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.reviewer_selection_mechanism.baseline import (
    merge_ordered_baseline,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge immutable formal-v1.22 ordered-verified baselines into E2",
    )
    parser.add_argument("--e2-run", required=True)
    parser.add_argument("--forgery-run", required=True)
    parser.add_argument("--removal-run", required=True)
    args = parser.parse_args()
    result = merge_ordered_baseline(
        args.e2_run, args.forgery_run, args.removal_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
