from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Iterable

from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.core.seeds import derive_seed


def load_val_images(annotation_path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(annotation_path).read_text(encoding="utf-8"))
    rows = payload.get("images")
    if not isinstance(rows, list) or len(rows) != 5000:
        raise ValueError("instances_val2017.json must contain exactly 5000 images")
    normalized = sorted(rows, key=lambda row: int(row["id"]))
    if len({int(row["id"]) for row in normalized}) != 5000:
        raise ValueError("COCO image IDs must be unique")
    return normalized


def shuffled_images(images: Iterable[dict[str, Any]], *identifiers: str, pilot: bool = False) -> list[dict[str, Any]]:
    values = list(images)
    namespace = "budget_pilot" if pilot else "data_order"
    random.Random(derive_seed(namespace, *identifiers)).shuffle(values)
    return values


def allocate_val2017_roles(images: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    values = list(images)
    if len(values) != 5000:
        raise ValueError("val2017 role allocation requires all 5000 images")

    clean_order = shuffled_images(values, "coco2017", "val2017", "formal_clean_prior")
    formal_target_order = shuffled_images(values, "coco2017", "val2017", "formal_forgery_target")
    formal_target_ids = {int(row["id"]) for row in formal_target_order[:200]}
    pilot_candidates = [row for row in shuffled_images(
        values, "data_order", "coco2017", "val2017", "pilot_forgery_target", pilot=True
    ) if int(row["id"]) not in formal_target_ids]
    pilot_clean_order = shuffled_images(
        values, "data_order", "coco2017", "val2017", "pilot_clean_prior", pilot=True
    )
    return {
        "formal_targets": formal_target_order[:200],
        "formal_clean": clean_order,
        "pilot_targets": pilot_candidates[:100],
        "pilot_clean": pilot_clean_order[:500],
    }


def image_record(image: dict[str, Any], root: Path) -> dict[str, Any]:
    path = root / str(image["file_name"])
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "image_id": int(image["id"]),
        "file_name": image["file_name"],
        "path": str(path.resolve()),
        "width": int(image["width"]),
        "height": int(image["height"]),
        "sha256": sha256_file(path),
    }


def materialize_manifests(images: Iterable[dict[str, Any]], val_root: str | Path) -> dict[str, list[dict[str, Any]]]:
    root = Path(val_root).resolve()
    allocations = allocate_val2017_roles(images)
    base = {int(row["id"]): image_record(row, root) for row in images}

    formal_targets = [dict(base[int(image["id"])], key_id=f"key_{index:03d}") for index, image in enumerate(allocations["formal_targets"])]
    formal_clean = [dict(base[int(image["id"])], key_id=f"key_{index // 25:03d}", clean_index=index % 25) for index, image in enumerate(allocations["formal_clean"])]
    pilot_targets = [dict(base[int(image["id"])], key_id=f"pilot_key_{index:03d}") for index, image in enumerate(allocations["pilot_targets"])]
    pilot_clean = [dict(base[int(image["id"])], key_id=f"pilot_key_{index // 5:03d}", clean_index=index % 5) for index, image in enumerate(allocations["pilot_clean"])]

    target_by_id = {row["image_id"]: row["key_id"] for row in formal_targets}
    clean_by_id = {row["image_id"]: (row["key_id"], row["clean_index"]) for row in formal_clean}
    overlap = []
    for image in sorted(images, key=lambda row: int(row["id"])):
        record = dict(base[int(image["id"])])
        clean_key, clean_index = clean_by_id[record["image_id"]]
        record.update({
            "is_forgery_target": record["image_id"] in target_by_id,
            "forgery_key_id": target_by_id.get(record["image_id"], ""),
            "is_clean_prior": True,
            "clean_prior_key_id": clean_key,
            "clean_index": clean_index,
        })
        overlap.append(record)
    return {
        "formal_forgery_target_manifest.csv": formal_targets,
        "formal_clean_prior_manifest.csv": formal_clean,
        "p0_forgery_target_manifest.csv": pilot_targets,
        "p0_clean_prior_manifest.csv": pilot_clean,
        "data_role_overlap.csv": overlap,
    }


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty manifest")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    temporary.replace(destination)
