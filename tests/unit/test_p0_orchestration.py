from latent_space_aggregation_attacks.core import p0


def test_p0_layout_has_no_persistent_image_directories(tmp_path):
    layout = p0._ensure_layout(tmp_path / "run")
    assert (layout / "resume_state").is_dir()
    assert not (layout / "reference_images").exists()
    assert not (layout / "final_images_visualization_keys").exists()
    assert not (layout / "figures").exists()


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
    result=p0.run_p0(config={"key_count":50},assets_lock=lock,output_root=tmp_path,run_id="run",smoke_only=False,project_root=tmp_path)
    assert calls==[("smoke",2),("p0",50)]
    assert result["status"]=="P0_COMPLETE"


def test_p0_smoke_only_does_not_start_full(monkeypatch, tmp_path):
    monkeypatch.setattr(p0,"_require_gpu_runtime",lambda: None)
    monkeypatch.setattr(p0,"load_target_pipeline",lambda model,offline: object())
    monkeypatch.setattr(p0,"load_proxy_vae",lambda model,offline: object())
    calls=[]
    monkeypatch.setattr(p0,"_run_stage",lambda **kwargs: (calls.append(kwargs["stage"]) or (tmp_path,[])))
    lock=asset_lock()
    result=p0.run_p0(config={},assets_lock=lock,output_root=tmp_path,run_id="run",smoke_only=True,project_root=tmp_path)
    assert calls==["smoke"]
    assert result["status"]=="SMOKE_PASSED"


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
