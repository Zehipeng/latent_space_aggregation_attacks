"""Pre-attack semantic assignment, independent of attack outcomes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..formal.common import assets_by_name, formal_inputs, open_rgb, atomic_png, atomic_csv, canonical_512, read_csv
from ..core.hashing import sha256_file


def select_covers(annotation, image_root, subjects):
    categories = {item["name"]: item["id"] for item in annotation["categories"]}
    wanted = {categories[name] for name in subjects.values()}
    by_image = {}
    for item in annotation["annotations"]:
        by_image.setdefault(item["image_id"], set()).add(item["category_id"])
    images = {item["id"]: item for item in annotation["images"]}
    targets = {}
    for key, subject in subjects.items():
        category = categories[subject]
        candidates = sorted(image_id for image_id, ids in by_image.items()
                            if ids & wanted == {category})
        if not candidates:
            raise RuntimeError(f"No COCO example for locked subject {subject}")
        image_id = candidates[0]
        path = Path(image_root) / images[image_id]["file_name"]
        if not path.is_file():
            raise RuntimeError(f"Missing locked cover: {path}")
        targets[key] = {"key_id": key, "image_id": str(image_id), "path": str(path), "subject": subject}
    return targets


def build_inputs(assets, settings):
    by_name = assets_by_name(assets)
    prompts, targets, clean = formal_inputs(by_name)
    annotations = json.loads(Path(by_name["coco-2017-annotations"]["path"]).read_text(encoding="utf-8"))
    targets.update(select_covers(annotations, by_name["coco-2017-val"]["path"], settings["forgery_subjects"]))
    for key, prompt in settings["removal_prompts"].items():
        prompts[key] = [{**row, "prompt": prompt,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
                       for row in prompts[key]]
    return prompts, targets, clean


def verify_originals(root, rows):
    hashes = set()
    thumbnails = []
    for row in rows:
        image = open_rgb(root / row["original_path"])
        digest = hashlib.sha256(image.tobytes()).hexdigest()
        if digest in hashes:
            raise RuntimeError("Duplicate original pixels across visual samples")
        hashes.add(digest)
        small = np.asarray(image.resize((32, 32)), dtype=np.float32)
        if any(np.mean(np.abs(small - previous)) < 3 for previous in thumbnails):
            raise RuntimeError("Near-duplicate original samples require review")
        thumbnails.append(small)
    if len(rows) != 10:
        raise RuntimeError("Expected ten distinct original samples")


def freeze_originals(root, settings, covers):
    references = read_csv(root / "shared_preparation/manifests/reference_manifest.csv")
    rows = []
    for group, keys in settings["group_keys"].items():
        for key in keys:
            if group.startswith("forgery"):
                source = covers[key]["path"]
                image = canonical_512(open_rgb(source))
                content = covers[key]["subject"]
            else:
                reference = next(row for row in references if row["key_id"] == key
                                 and int(row["selected_reference_index"]) == 0)
                source = root / "shared_preparation" / reference["image_path"]
                if sha256_file(source) != reference["image_sha256"]:
                    raise RuntimeError("Removal original reference hash mismatch")
                image = open_rgb(source)
                content = settings["removal_prompts"][key]
            relative = Path("images/originals") / f"{key}.png"
            digest = atomic_png(root / relative, image)
            rows.append({"group": group, "key_id": key, "content": content,
                         "source_path": str(source), "original_path": relative.as_posix(),
                         "original_sha256": digest})
    verify_originals(root, rows)
    atomic_csv(root / "original_manifest.csv", rows)
