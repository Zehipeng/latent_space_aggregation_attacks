from pathlib import Path

import pytest
import yaml

from latent_space_aggregation_attacks.core.config import load_config


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "configs/budget_pilot/p0_forgery.yaml",
        ROOT / "configs/budget_pilot/p0_removal.yaml",
        ROOT / "configs/diagnostics/removal_beta_1p5_10key.yaml",
    ],
)
def test_v114_p0_and_diagnostic_configs_are_archived(path):
    with pytest.raises(ValueError, match="protocol_version"):
        load_config(path)


def test_v116_formal_config_is_frozen_and_uses_outputs_root():
    config = load_config(ROOT / "configs/formal/formal_v1p16.yaml")
    assert config["T_forgery_formal"] == 1500
    assert config["T_removal_formal"] == 1500
    assert config["beta_values"] == [1.0, 1.5, 2.0]
    assert config["main_beta"] == 1.0
    assert config["trajectory_every"] == 100
    assert config["output_root"] == "/root/autodl-tmp/outputs"


def test_v114_unfrozen_formal_template_is_archived():
    with pytest.raises(ValueError, match="protocol_version"):
        load_config(ROOT / "configs/formal/formal_template.yaml")


def test_wrong_formal_budget_is_rejected(tmp_path):
    value = yaml.safe_load((ROOT / "configs/formal/formal_v1p16.yaml").read_text(encoding="utf-8"))
    value["T_forgery_formal"] = 1400
    path = tmp_path / "bad_budget.yaml"
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(ValueError, match="both task budgets"):
        load_config(path)


def test_formal_online_detection_is_rejected(tmp_path):
    value = yaml.safe_load((ROOT / "configs/formal/formal_v1p16.yaml").read_text(encoding="utf-8"))
    value["online_detection"] = True
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(ValueError, match="online detection"):
        load_config(path)


def test_chinese_formal_output_root_is_rejected(tmp_path):
    value = yaml.safe_load((ROOT / "configs/formal/formal_v1p16.yaml").read_text(encoding="utf-8"))
    value["output_root"] = "/root/autodl-tmp/实验结果"
    path = tmp_path / "bad_output_root.yaml"
    path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="output_root"):
        load_config(path)
