from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
KB = (ROOT / "src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")


def test_knowledge_base_is_top_level_workspace():
    assert '"Knowledge Base"' in APP
    assert '"Taxonomy", "AI Review"' not in APP
    assert "KnowledgeBaseWorkspace" in APP


def test_knowledge_base_contains_independent_providers_and_data_view():
    assert "MultimodalAIReviewWorkspace" in KB
    assert 'self._tabs.addTab(self._ai_review_hub, "AI Review")' in KB
    assert "Taxonomy · GBIF" in KB
    assert "All Knowledge" in KB
    assert "asset_taxonomy_enrichments" in KB
    assert "ai_suggestions" in KB


def test_knowledge_base_has_independent_geometry_and_lifecycle():
    assert "knowledgeBaseMainSplitter" in KB
    assert "ui/knowledge_base/main_splitter" in KB
    assert "def activate(" in KB
    assert "def deactivate(" in KB


def test_legacy_routes_deep_link_into_knowledge_base():
    assert 'if name == "AI Review"' in APP
    assert "show_ai_review()" in APP
    assert 'elif name == "Taxonomy"' in APP
    assert "show_taxonomy()" in APP
