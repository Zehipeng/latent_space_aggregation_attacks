from pathlib import Path
import pytest,yaml
from latent_space_aggregation_attacks.core.config import load_config
ROOT=Path(__file__).resolve().parents[2]
def test_p0_config_is_valid():
    config = load_config(ROOT / "configs/budget_pilot/p0.yaml")
    assert config["master_seed"] == 205
    assert config["key_count"] == 50
    assert config["N_values"] == [5]
    assert config["lambda_values"] == [10000.0]
    assert config["beta_values"] == [1.0]
    assert config["visualization_key_ids"] == ["pilot_key_000", "pilot_key_001"]
    assert config["retain_non_visualization_images"] is False
    assert config["watermark_runtime"]["tree_ring"]["radius"] == 16
    assert config["reference_validity"] == {
        "selection_policy": "first_accepted_from_preregistered_candidates",
        "candidate_limit": 64,
        "require_all_selected_accepted": True,
    }
def test_unfrozen_formal_config_fails_closed():
    with pytest.raises(ValueError,match="not frozen"): load_config(ROOT/"configs/formal/formal_template.yaml")
def test_formal_online_detection_is_rejected(tmp_path):
    value=yaml.safe_load((ROOT/"configs/formal/formal_template.yaml").read_text(encoding="utf-8")); value["T_formal"]=1000; value["online_detection"]=True
    path=tmp_path/"bad.yaml"; path.write_text(yaml.safe_dump(value),encoding="utf-8")
    with pytest.raises(ValueError,match="online detection"): load_config(path)
