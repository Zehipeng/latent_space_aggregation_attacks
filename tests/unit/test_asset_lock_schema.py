import json

import pytest

from latent_space_aggregation_attacks.models.asset_lock import load_and_verify_assets


def test_legacy_asset_lock_is_rejected(tmp_path):
    path = tmp_path / "assets.lock.json"
    path.write_text(json.dumps({"schema_version": 1, "assets": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="legacy asset-lock"):
        load_and_verify_assets(path)
