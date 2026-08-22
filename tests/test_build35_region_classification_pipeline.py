from pathlib import Path


def test_photo_enrichment_exposes_detector_to_classifier_pipeline() -> None:
    workspace = Path(
        "src/natureai_next/application/enrichment_workspace.py"
    ).read_text(encoding="utf-8")
    dialog = Path(
        "src/natureai_next/ui/qt/capability_execution.py"
    ).read_text(encoding="utf-8")
    media = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")

    assert "def run_region_pipeline_async(" in workspace
    assert "image.crop((left, top, right, bottom)).save(crop_path)" in workspace
    assert '"detector_capability_id": detector_id' in workspace
    assert "Classify every detected region" in dialog
    assert "request.region_classifier_id" in media
