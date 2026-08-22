from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = (ROOT / "src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")
AI = (ROOT / "src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
MODELS = (ROOT / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")
APP = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")


def test_knowledge_base_exposes_media_specific_review_tabs():
    for label in ("Overview", "Photos", "Sounds", "Videos", "Documents", "Comparisons", "Accepted Knowledge"):
        assert f'"{label}"' in KB
    assert "MultimodalAIReviewWorkspace" in KB


def test_photo_review_distinguishes_generation_model_from_result_provenance():
    assert "Current generation model" in AI
    assert "review_overview" in AI
    assert '("Model", detail.model_variant_public_id)' in AI
    assert "Image used for this rating" in AI


def test_model_activation_is_described_by_compatible_capability():
    assert "Multiple models" in MODELS
    assert "may be active at the same time" in MODELS
    assert "active for compatible capabilities" in MODELS
    assert "Active for:" in MODELS
    assert "Started from:" in MODELS


def test_status_bar_names_multimodal_review():
    assert "multimodal AI Review" in APP
