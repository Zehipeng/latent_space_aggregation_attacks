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

def synthetic_rows():
    rows = [{"task":"forgery", "watermark":wm, "method":m, "key_id":f"key_{i:03d}",
        "step":s, "eligible":i == 0, "score":.2 if i == 0 else .9}
        for wm in EXPECTED["watermarks"] for m in EXPECTED["methods"]
        for i in range(40) for s in range(0,151,10)]
    return rows

def test_summary_all_40_arithmetic_mean():
    result = summarize(synthetic_rows())
    assert len(result) == 64
    assert all(r["sample_n"] == 40 and r["center"] == pytest.approx((.2 + 39*.9)/40) for r in result)
    assert all(r["aggregation"] == "arithmetic_mean" and "lower" not in r and "upper" not in r for r in result)

@pytest.mark.parametrize("problem", ["missing", "duplicate", "nan", "out_of_range"])
def test_summary_rejects_incomplete_or_invalid_data(problem):
    rows = synthetic_rows()
    if problem == "missing":
        rows.pop()
    elif problem == "duplicate":
        rows[-1] = rows[0].copy()
    else:
        rows[0]["score"] = float("nan") if problem == "nan" else 1.1
    with pytest.raises(ValueError):
        summarize(rows)

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
