import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_visual_model_catalog_has_offline_yolo_and_sam():
    models={m["key"]:m for m in json.loads((ROOT/"src/natureai_next/resources/models.json").read_text())["models"]}
    for key in ("yolo11n-detect","yolo11n-segment","sam-vit-b"):
        assert models[key]["offline_execution"] is True
        assert "enrichment performs no network access" in models[key]["installation_contract"]

def test_visual_model_worker_has_persistent_weights_and_dispatch():
    text=(ROOT/"src/natureai_next/synthesis_core/optional_model_worker.py").read_text()
    for token in ("yolo11n.pt","yolo11n-seg.pt","sam_vit_b_01ec64.pth","_run_yolo","_run_sam"):
        assert token in text

def test_visual_capabilities_are_producer_neutral():
    text=(ROOT/"src/natureai_next/synthesis_core/optional_models.py").read_text()
    assert 'CanonicalShape.SEGMENTATION.value' in text
    assert 'aperture.yolo11-detect' in text
    assert 'aperture.sam-vit-b' in text
