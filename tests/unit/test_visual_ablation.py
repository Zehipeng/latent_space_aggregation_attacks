import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from latent_space_aggregation_attacks.core.atomic_io import atomic_write_json
from latent_space_aggregation_attacks.formal.common import atomic_png
from latent_space_aggregation_attacks.visual.common import EXPECTED, load_settings, plan, semantic_difference, verified_record
from latent_space_aggregation_attacks.visual.report import finalize

PROJECT = Path(__file__).resolve().parents[2]


def test_approved_matrix_deduplicates_main_condition():
    conditions, views = plan(EXPECTED)
    assert len(conditions) == 12
    assert sum(c["task"] == "forgery" for c in conditions) == 5
    assert sum(c["task"] == "removal" for c in conditions) == 7
    assert len(views) == 30
    by_id = {c["condition_id"]: c for c in conditions}
    for view in views:
        condition = by_id[view["condition_id"]]
        if view["factor"] != "lambda": assert condition["lambda"] == 10000
        if view["factor"] != "N": assert condition["N"] == 5
        if condition["task"] == "removal" and view["factor"] != "beta":
            assert condition["beta"] == 1.5
    main = [v for v in views if v["key_id"] == "key_000" and
            v["condition_id"] == "removal_N5_lambda10000_beta1.5"]
    assert len(main) == 3


def test_difference_matches_float_tensor_conversion_without_uint8_wrap():
    original = Image.fromarray(np.array([[[250, 0, 100], [20, 50, 255]]], dtype=np.uint8))
    final = Image.fromarray(np.array([[[0, 255, 101], [20, 40, 0]]], dtype=np.uint8))
    expected = (np.abs(np.asarray(final).astype(np.float32)/255 -
                       np.asarray(original).astype(np.float32)/255)*255).astype(np.uint8)
    actual = np.asarray(semantic_difference(final, original))
    np.testing.assert_array_equal(actual, expected)
    assert actual[0, 0, 0] == 250
    assert actual[0, 0, 1] == 255
    assert np.asarray(semantic_difference(original, original)).sum() == 0
    with pytest.raises(ValueError): semantic_difference(final.resize((4, 4)), original)


def test_settings_reject_unapproved_changes(tmp_path):
    import yaml
    path = tmp_path / "settings.yaml"
    changed = {**EXPECTED, "main_lambda": 20000}
    path.write_text(yaml.safe_dump(changed), encoding="utf-8")
    with pytest.raises(ValueError): load_settings(path)


def test_finalize_requires_all_units_and_valid_image_hashes(tmp_path):
    with pytest.raises(RuntimeError): finalize(tmp_path, EXPECTED)
    conditions, _ = plan(EXPECTED)
    image = Image.new("RGB", (2, 2), (1, 2, 3))
    for condition in conditions:
        for key in EXPECTED["key_ids"]:
            row = {**condition, "key_id": key, "final_step": 150}
            for name in ("original", "final", "difference"):
                path = Path("images") / condition["condition_id"] / key / f"{name}.png"
                row[f"{name}_sha256"] = atomic_png(tmp_path / path, image)
                row[f"{name}_path"] = path.as_posix()
            atomic_write_json(tmp_path / "units" / condition["condition_id"] / f"{key}.json", row)
    finalize(tmp_path, EXPECTED)
    report = json.loads((tmp_path / "visual_report.json").read_text())
    assert report["unique_attack_units"] == 24
    assert report["panel_rows"] == 30
    record = tmp_path / "units" / conditions[0]["condition_id"] / "key_000.json"
    row = verified_record(record, tmp_path)
    (tmp_path / row["final_path"]).write_bytes(b"corrupt")
    assert verified_record(record, tmp_path) is None
    with pytest.raises(RuntimeError): finalize(tmp_path, EXPECTED)


def test_cli_dry_run_does_not_need_assets_or_gpu():
    result = subprocess.run([sys.executable, str(PROJECT / "scripts/run_visual_ablation.py"),
                             "--dry-run", "--assets-lock", "does-not-exist.json"],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["attack_units"] == 24


def test_attack_import_does_not_load_watermark_detectors():
    code = "import sys; import latent_space_aggregation_attacks.visual.attack; assert not any(k.startswith('latent_space_aggregation_attacks.watermarks') for k in sys.modules)"
    import os
    env = {**os.environ, "PYTHONPATH": str(PROJECT / "src")}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_preparation_filters_only_ringid_cross_model_without_mutating_protocol(monkeypatch, tmp_path):
    from latent_space_aggregation_attacks.visual import prepare as module
    original = {"model_settings": ["same", "cross"], "watermarks": ["tree_ring", "ringid", "gaussian_shading"],
                "resolved_config_hash": "source"}
    calls = []
    monkeypatch.setattr(module, "prepare_formal_removal", lambda **kwargs: calls.append(kwargs) or {})
    module.prepare(original, {}, tmp_path, "visual_test", PROJECT, EXPECTED)
    assert calls[0]["config"]["watermarks"] == ["ringid"]
    assert calls[0]["config"]["model_settings"] == [EXPECTED["model_setting"]]
    assert calls[0]["key_ids"] == ["key_000", "key_001"]
    assert calls[0]["run_dir"] == tmp_path / "shared_preparation"
    assert original["resolved_config_hash"] == "source"
    assert len(original["watermarks"]) == 3
