from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from latent_space_aggregation_attacks.analysis.reliability import (
    PAIRED_OUTPUT_FIELDS,
    detection_rows,
    normalize_row,
    paired_comparison_rows,
    summarize_conditions,
)
from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.formal.common import atomic_csv, read_csv


def _input(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("input must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    path = Path(raw_path).resolve()
    if not label or not path.is_file():
        raise argparse.ArgumentTypeError(f"invalid input: {value}")
    return label, path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E1 post-hoc statistical reliability analysis",
    )
    parser.add_argument(
        "--input", action="append", required=True, type=_input,
        metavar="LABEL=FINAL_PER_KEY_METRICS.CSV",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--paired-bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=205)
    args = parser.parse_args()
    if args.bootstrap_replicates < 0 or args.paired_bootstrap_replicates < 0:
        parser.error("bootstrap replicate counts must be non-negative")
    if not 0 < args.confidence < 1:
        parser.error("confidence must be between zero and one")

    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    normalized = []
    inputs = []
    for label, path in args.input:
        source_rows = read_csv(path)
        normalized.extend(normalize_row(row, label) for row in source_rows)
        inputs.append({
            "label": label,
            "path": str(path),
            "sha256": sha256_file(path),
            "row_count": len(source_rows),
        })
    if not normalized:
        raise RuntimeError("No rows were loaded")

    condition_rows = summarize_conditions(
        normalized,
        bootstrap_replicates=args.bootstrap_replicates,
        confidence=args.confidence,
        master_seed=args.seed,
    )
    paired_rows = paired_comparison_rows(
        normalized,
        bootstrap_replicates=args.paired_bootstrap_replicates,
        confidence=args.confidence,
        master_seed=args.seed,
    )
    signal_rows = detection_rows(normalized)
    atomic_csv(output / "e1_condition_reliability.csv", condition_rows)
    atomic_csv(
        output / "e1_paired_comparisons.csv",
        paired_rows,
        list(PAIRED_OUTPUT_FIELDS),
    )
    atomic_csv(output / "e1_detection_signal_per_key.csv", signal_rows)
    manifest = {
        "status": "COMPLETE",
        "analysis": "E1 statistical reliability and residual detector signal",
        "inputs": inputs,
        "input_row_count": len(normalized),
        "condition_count": len(condition_rows),
        "paired_result_count": len(paired_rows),
        "confidence": args.confidence,
        "ASR_interval": "Wilson",
        "continuous_interval": "percentile bootstrap of the mean",
        "bootstrap_replicates": args.bootstrap_replicates,
        "paired_bootstrap_replicates": args.paired_bootstrap_replicates,
        "seed": args.seed,
        "outputs": {
            path.name: sha256_file(path)
            for path in (
                output / "e1_condition_reliability.csv",
                output / "e1_paired_comparisons.csv",
                output / "e1_detection_signal_per_key.csv",
            )
        },
        "notes": [
            "ASR uses eligible samples only.",
            "Quality and detector-signal summaries use all available finite rows.",
            "Paired effects are left minus right and are paired by key_id.",
            "No p-values or multiplicity claims are emitted by this analysis.",
        ],
    }
    atomic_write_json(output / "e1_analysis_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
