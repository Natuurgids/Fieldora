from pathlib import Path


def test_build33_photo_review_uses_approved_evidence_layout():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
    for object_name in (
        'photoAIReviewWorkspace',
        'photoReviewFilters',
        'photoSuggestionQueue',
        'photoSourcePreview',
        'photoReviewModelInputCard',
        'photoModelInputPreview',
        'photoReviewDecisionPanel',
        'photoReviewMainSplitter',
    ):
        assert object_name in source
    assert 'QGroupBox("Source photograph")' in source
    assert 'QGroupBox("Image used for this rating (model input)")' in source
    assert 'QGroupBox("AI suggestion")' in source


def test_photo_review_hub_retains_bioclip_workflow_and_exposes_canonical_results():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")
    assert 'self._tabs.addTab(photo_review, "Photos")' in source
    assert 'self._tabs.addTab(self._canonical_photo_review, "Photo Results")' in source
    assert 'self._photo_review = photo_review' in source
    assert "self._overview = _AIReviewOverview(photo_review)" in source
