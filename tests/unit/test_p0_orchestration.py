from latent_space_aggregation_attacks.core import p0


def asset_lock():
    return {"assets":[
        {"name":"stable-diffusion-2-base","path":"/target","revision":"f5bc1bd97485577aa0b946fa8a9004e2ec147402"},
        {"name":"stable-diffusion-v1-4","path":"/proxy","revision":"133a221b8aa7292a167afc5127cb63fb5005638b"},
        {"name":"tree-ring-watermark","path":"/tree"}, {"name":"RingID","path":"/ring"},
        {"name":"Gaussian-Shading","path":"/gs"}, {"name":"formal-protocol-v1.9-prompt-manifest","path":"/prompts"},
        {"name":"formal-protocol-v1.9-coco-manifests","path":"/coco"},
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
    result=p0.run_p0(config={},assets_lock=lock,output_root=tmp_path,run_id="run",smoke_only=False,project_root=tmp_path)
    assert calls==[("smoke",2),("p0",100)]
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
