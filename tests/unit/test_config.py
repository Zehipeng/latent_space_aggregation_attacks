from pathlib import Path
import pytest,yaml
from latent_space_aggregation_attacks.core.config import load_config
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.parametrize(("name", "task", "t_max"), [
    ("p0_forgery.yaml", "forgery", 3000),
    ("p0_removal.yaml", "removal", 15000),
])
def test_task_specific_p0_config_is_valid(name, task, t_max):
    config = load_config(ROOT / "configs/budget_pilot" / name)
    assert config["master_seed"] == 205
    assert config["key_count"] == 50
    assert config["N_values"] == [5]
    assert config["lambda_values"] == [10000.0]
    assert config["beta_values"] == [1.0]
    assert config["visualization_key_ids"] == []
    assert config["tasks"] == [task]
    assert config["T_max"] == t_max
    assert config["p0_storage"] == {
        "persist_reference_images": False,
        "persist_attack_images": True,
        "persist_asr_curve_images": True,
    }
    assert "retain_non_visualization_images" not in config
    assert config["watermark_runtime"]["tree_ring"]["radius"] == 16
    assert config["reference_validity"] == {
        "selection_policy": "first_accepted_from_preregistered_candidates",
        "candidate_limit": 64,
        "require_all_selected_accepted": True,
    }


def test_removal_beta_diagnostic_config_is_valid():
    config = load_config(ROOT / "configs/diagnostics/removal_beta_1p5_10key.yaml")
    assert config["key_count"] == 10
    assert config["tasks"] == ["removal"]
    assert config["main_beta"] == 1.5
    assert config["T_max"] == 3000
    assert config["online_detection"] is False
    assert config["diagnostic_storage"]["persist_checkpoint_images"] is False
def test_unfrozen_formal_config_fails_closed():
    with pytest.raises(ValueError,match="not frozen"): load_config(ROOT/"configs/formal/formal_template.yaml")
def test_formal_online_detection_is_rejected(tmp_path):
    value=yaml.safe_load((ROOT/"configs/formal/formal_template.yaml").read_text(encoding="utf-8")); value["T_forgery_formal"]=1000; value["T_removal_formal"]=1000; value["online_detection"]=True
    path=tmp_path/"bad.yaml"; path.write_text(yaml.safe_dump(value),encoding="utf-8")
    with pytest.raises(ValueError,match="online detection"): load_config(path)
