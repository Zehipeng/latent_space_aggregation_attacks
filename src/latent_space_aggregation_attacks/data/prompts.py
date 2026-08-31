from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path
from typing import Iterable

from latent_space_aggregation_attacks.core.seeds import derive_seed

PROMPT_COLUMNS = ("cohort", "key_id", "reference_index", "source_split", "source_row", "prompt_sha256", "prompt")


def prompt_row_order(row_count: int) -> list[int]:
    """Return the protocol-seeded, deterministic order of source prompt rows."""
    if row_count < 19_200:
        raise ValueError("Prompt train split must contain at least 19,200 rows")
    values = list(range(row_count))
    random.Random(derive_seed("data_order", "stable_diffusion_prompts", "train")).shuffle(values)
    return values


def build_prompt_rows(prompts: Iterable[str]) -> list[dict[str, str | int]]:
    """Assign disjoint 64-candidate banks to 100 pilot and 200 formal keys."""
    values = list(prompts)
    order = prompt_row_order(len(values))
    rows: list[dict[str, str | int]] = []
    offset = 0
    for cohort, count, prefix in (("pilot", 100, "pilot_key"), ("formal", 200, "key")):
        for key_index in range(count):
            for reference_index in range(64):
                source_row = order[offset]
                offset += 1
                prompt = str(values[source_row])
                rows.append({
                    "cohort": cohort,
                    "key_id": f"{prefix}_{key_index:03d}",
                    "reference_index": reference_index,
                    "source_split": "train",
                    "source_row": source_row,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "prompt": prompt,
                })
    return rows


def read_parquet_prompts(path: str | Path) -> list[str]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("pyarrow==15.0.2 is required to read the locked prompt parquet") from exc
    table = parquet.read_table(Path(path))
    if "Prompt" not in table.column_names:
        raise ValueError(f"Expected Prompt column, found {table.column_names}")
    values = table.column("Prompt").to_pylist()
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Prompt column contains blank or non-string values")
    return values


def write_prompt_manifest(path: str | Path, rows: Iterable[dict[str, object]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROMPT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    temporary.replace(destination)
