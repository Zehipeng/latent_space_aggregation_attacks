from pathlib import Path
def test_attack_package_does_not_import_detector_modules():
    root=Path(__file__).resolve().parents[2]/"src/latent_space_aggregation_attacks/methods"; text="\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.py"))
    assert "detect_p_value" not in text and "load_target_pipeline" not in text and "watermarks" not in text

def test_formal_attack_process_has_no_detector_dependency():
    root=Path(__file__).resolve().parents[2]
    text=(root/"src/latent_space_aggregation_attacks/core/formal_attack.py").read_text(encoding="utf-8")
    forbidden=("registered_adapter","load_target_pipeline",".detect(","watermarks")
    assert all(value not in text for value in forbidden)
