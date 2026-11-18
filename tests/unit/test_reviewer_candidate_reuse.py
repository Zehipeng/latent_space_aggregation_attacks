from pathlib import Path

import pytest

from latent_space_aggregation_attacks.core.hashing import sha256_file
from latent_space_aggregation_attacks.reviewer_selection_mechanism.reuse import (
    _materialize,
    _relative_image,
    _validate_rows,
)


def _rows(root: Path) -> list[dict[str, str]]:
    rows = []
    for index in range(64):
        relative = Path("prepared_inputs/candidate_bank/model/watermark/key_000") / (
            f"candidate_{index:02d}.png"
        )
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"candidate-{index}".encode())
        rows.append({
            "model_setting": "model",
            "watermark": "watermark",
            "key_id": "key_000",
            "candidate_index": str(index),
            "image_path": relative.as_posix(),
            "image_sha256": sha256_file(path),
        })
    return rows


def test_reuse_validates_complete_groups_and_hardlinks_images(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    rows = _rows(source)
    _validate_rows(
        rows, root=source, model="model", watermark="watermark", key_id="key_000",
    )
    first = rows[0]
    mode = _materialize(
        source / first["image_path"], destination / first["image_path"],
        first["image_sha256"], False,
    )
    assert mode == "hardlink"
    assert (source / first["image_path"]).stat().st_ino == (
        destination / first["image_path"]
    ).stat().st_ino


def test_reuse_rejects_incomplete_groups(tmp_path: Path) -> None:
    rows = _rows(tmp_path)[:-1]
    with pytest.raises(RuntimeError, match="64 rows"):
        _validate_rows(
            rows, root=tmp_path, model="model",
            watermark="watermark", key_id="key_000",
        )


def test_reuse_rejects_paths_outside_the_run(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsafe candidate image path"):
        _relative_image(tmp_path, "../outside.png")
