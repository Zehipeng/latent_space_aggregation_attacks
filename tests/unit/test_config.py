from pathlib import Path
import pytest,yaml
from latent_space_aggregation_attacks.core.config import load_config
ROOT=Path(__file__).resolve().parents[2]
def test_p0_config_is_valid(): assert load_config(ROOT/"configs/budget_pilot/p0.yaml")["master_seed"]==205
def test_unfrozen_formal_config_fails_closed():
    with pytest.raises(ValueError,match="not frozen"): load_config(ROOT/"configs/formal/formal_template.yaml")
def test_formal_online_detection_is_rejected(tmp_path):
    value=yaml.safe_load((ROOT/"configs/formal/formal_template.yaml").read_text(encoding="utf-8")); value["T_formal"]=1000; value["online_detection"]=True
    path=tmp_path/"bad.yaml"; path.write_text(yaml.safe_dump(value),encoding="utf-8")
    with pytest.raises(ValueError,match="online detection"): load_config(path)
