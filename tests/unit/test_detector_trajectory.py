import ast
from pathlib import Path
import pytest
from latent_space_aggregation_attacks.trajectory.common import EXPECTED, units, load_settings, summarize

def test_contract():
    project = Path(__file__).resolve().parents[2]
    assert load_settings(project / "configs/diagnostics/single_img_vs_fr_la_trajectory_v1.yaml") == EXPECTED
    assert len(units("forgery")) == len(units("removal")) == 160
    assert 2 * len(units("forgery")) * len(range(0, 151, 10)) == 5120
    with pytest.raises(ValueError):
        units("other")

def test_detector_free_imports():
    project = Path(__file__).resolve().parents[2]
    source = project / "src/latent_space_aggregation_attacks/trajectory/attack.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assert all("watermark" not in (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))

def test_summary_eligibility():
    rows = [{"task":"forgery", "watermark":wm, "method":m, "key_id":f"key_{i:03d}",
        "step":s, "eligible":i == 0, "score":.2 if i == 0 else .9}
        for wm in EXPECTED["watermarks"] for m in EXPECTED["methods"]
        for i in range(40) for s in range(0,151,10)]
    result = summarize(rows)
    assert len(result) == 64
    assert all(r["eligible_n"] == 1 and r["center"] == pytest.approx(.2) for r in result)

def test_every_ten_updates_without_detector():
    torch = pytest.importorskip("torch")
    from types import SimpleNamespace
    from latent_space_aggregation_attacks.attack import optimize_fixed_budget
    class VAE(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.ones(1))
            self.config = SimpleNamespace(scaling_factor=1.0)
        def encode(self, value):
            return SimpleNamespace(latent_dist=SimpleNamespace(mode=lambda: value * self.weight))
    steps = []
    result = optimize_fixed_budget(torch.zeros(1,1,2,2), torch.ones(1,1,2,2), VAE(),
        lambda_pixel=0, learning_rate=.02, final_step=150, checkpoint_every=10,
        checkpoint_callback=lambda step, image, history: steps.append(step))
    assert steps == list(range(10,151,10))
    assert result.final_step == 150 and not result.stopped_early
