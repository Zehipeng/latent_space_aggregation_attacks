from latent_space_aggregation_attacks.archive import p0_runtime as p0


def test_p0_layout_separates_attack_outputs_from_nonpersistent_references(tmp_path):
    layout = p0._ensure_layout(tmp_path / "run")
    assert (layout / "resume_state").is_dir()
    assert not (layout / "reference_images").exists()
    assert (layout / "final_images").is_dir()
    assert (layout / "figures").is_dir()


def test_p0_curve_plot_writes_only_the_task_specific_png(tmp_path):
    csv_path = tmp_path / "pilot_asr_by_step.csv"
    rows = []
    for watermark in ("tree_ring", "ringid", "gaussian_shading"):
        rows.extend([
            {"task": "forgery", "watermark": watermark, "step": 100, "cumulative_asr": 0.25},
            {"task": "forgery", "watermark": watermark, "step": 200, "cumulative_asr": 0.5},
        ])
    p0._atomic_csv(csv_path, rows, ["task", "watermark", "step", "cumulative_asr"])

    outputs = p0._plot_p0_curves(csv_path, tmp_path / "figures")

    assert [path.name for path in outputs] == ["pilot_forgery_asr_curve.png"]
    assert all(path.is_file() and path.stat().st_size > 0 for path in outputs)


def asset_lock():
    return {"assets":[
        {"name":"stable-diffusion-2-base","path":"/target","revision":"f5bc1bd97485577aa0b946fa8a9004e2ec147402"},
        {"name":"stable-diffusion-v1-4","path":"/proxy","revision":"133a221b8aa7292a167afc5127cb63fb5005638b"},
        {"name":"tree-ring-watermark","path":"/tree"}, {"name":"RingID","path":"/ring"},
        {"name":"Gaussian-Shading","path":"/gs"}, {"name":"formal-protocol-v1.10-prompt-manifest","path":"/prompts"},
        {"name":"formal-protocol-v1.10-coco-manifests","path":"/coco"},
    ]}


def test_p0_runs_smoke_before_full(monkeypatch, tmp_path):
    calls=[]
    monkeypatch.setattr(p0,"_require_gpu_runtime",lambda: None)
    monkeypatch.setattr(p0,"load_target_pipeline",lambda model,offline: object())
    monkeypatch.setattr(p0,"load_proxy_vae",lambda model,offline: object())
    def fake_stage(**kwargs):
        calls.append((kwargs["stage"],len(kwargs["key_ids"])))
        return tmp_path/kwargs["stage"],[]
    monkeypatch.setattr(p0,"_run_stage",fake_stage)
    lock=asset_lock()
    result=p0.run_p0(config={"key_count":50,"tasks":["forgery"]},assets_lock=lock,output_root=tmp_path,run_id="run",smoke_only=False,project_root=tmp_path,expected_task="forgery")
    assert calls==[("smoke",2),("p0",50)]
    assert result["status"]=="P0_COMPLETE"


def test_p0_smoke_only_does_not_start_full(monkeypatch, tmp_path):
    monkeypatch.setattr(p0,"_require_gpu_runtime",lambda: None)
    monkeypatch.setattr(p0,"load_target_pipeline",lambda model,offline: object())
    monkeypatch.setattr(p0,"load_proxy_vae",lambda model,offline: object())
    calls=[]
    monkeypatch.setattr(p0,"_run_stage",lambda **kwargs: (calls.append(kwargs["stage"]) or (tmp_path,[])))
    lock=asset_lock()
    result=p0.run_p0(config={"tasks":["removal"]},assets_lock=lock,output_root=tmp_path,run_id="run",smoke_only=True,project_root=tmp_path,expected_task="removal")
    assert calls==["smoke"]
    assert result["status"]=="SMOKE_PASSED"


def test_p0_entry_point_rejects_the_other_task(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="requires tasks"):
        p0.run_p0(
            config={"tasks": ["removal"]}, assets_lock=asset_lock(), output_root=tmp_path,
            run_id="run", smoke_only=True, project_root=tmp_path, expected_task="forgery",
        )


def test_removal_diagnostic_summary_contains_only_requested_metrics(tmp_path):
    rows = []
    for watermark in ("tree_ring", "ringid", "gaussian_shading"):
        rows.append({
            "watermark": watermark, "eligible": True, "success": watermark == "tree_ring",
            "l2": 1.0, "linf": 0.1, "LPIPS": 0.2, "SSIM": 0.9, "PSNR": 30.0,
            "optimization_progress_pct": 50.0,
        })
    path = tmp_path / "summary.csv"
    p0._write_removal_diagnostic_summary(rows, path)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "Watermark,Model,beta,eligible_n,ASR,l2,linf,LPIPS,SSIM,PSNR,optimization_progress_pct"


def test_reference_selection_uses_first_accepted_candidates_and_reuses_artifacts(tmp_path):
    from types import SimpleNamespace
    from PIL import Image

    class Adapter:
        def __init__(self): self.generated = 0
        def generate(self, prompt, key, seed):
            self.generated += 1
            return Image.new("RGB", (2, 2), color=(int(prompt), 0, 0))
        def detect(self, image, key):
            value = image.getpixel((0, 0))[0]
            return SimpleNamespace(score=float(value), score_name="test_score", accepted=value in {1, 3})

    candidates = [
        {"reference_index": str(index), "prompt": str(index), "prompt_sha256": f"hash-{index}"}
        for index in range(4)
    ]
    adapter = Adapter()
    control_path = tmp_path / "manifests" / "reference_selection_control.csv"
    images, selected, controls = p0._select_valid_references(
        adapter=adapter, key=object(), watermark="tree_ring", key_id="pilot_key_000",
        candidate_rows=candidates, reference_count=2, candidate_limit=4,
        run_dir=tmp_path, run_id="run", stage="smoke", control_path=control_path,
        control_rows=[],
    )
    assert len(images) == 2
    assert [row["reference_index"] for row in selected] == ["1", "3"]
    assert [row["candidate_index"] for row in controls] == [0, 1, 2, 3]
    assert all(row["accepted"] for row in controls if row["selected"])
    assert adapter.generated == 4

    images2, selected2, controls2 = p0._select_valid_references(
        adapter=adapter, key=object(), watermark="tree_ring", key_id="pilot_key_000",
        candidate_rows=candidates, reference_count=2, candidate_limit=4,
        run_dir=tmp_path, run_id="run", stage="smoke", control_path=control_path,
        control_rows=controls,
    )
    assert len(images2) == 2
    assert [row["reference_index"] for row in selected2] == ["1", "3"]
    assert controls2 == controls
    assert adapter.generated == 6
    assert not list(tmp_path.rglob("*.png"))
