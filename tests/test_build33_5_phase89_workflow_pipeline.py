from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reusable_workflow_graph_and_unified_pipeline_are_present():
    graph = (ROOT / "src/natureai_next/ui/qt/workflow_graph.py").read_text(encoding="utf-8")
    assert "class WorkflowGraphWidget" in graph
    assert "class EnrichmentPipelineWidget" in graph
    for stage in ("Media evidence", "AI analysis", "Candidate", "Knowledge sources", "Knowledge Base review", "Accepted observation"):
        assert stage in graph


def test_phase89_surfaces_share_the_graph_components():
    model = (ROOT / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")
    sources = (ROOT / "src/natureai_next/ui/qt/knowledge_sources.py").read_text(encoding="utf-8")
    enrichment = (ROOT / "src/natureai_next/ui/qt/enrichment.py").read_text(encoding="utf-8")
    assert "WorkflowGraphWidget" in model
    assert "EnrichmentPipelineWidget" in sources
    assert "EnrichmentPipelineWidget" in enrichment
    assert "set_counts(presentation.pending_count" in enrichment
