from pathlib import Path


def test_observations_workspace_exposes_bulk_review_controls():
    source=Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    block=source[source.index("class Observations(Page):"):source.index("class AIChatWorkspace(Page):")]
    for label in ("Accept selected","Reject selected","Defer selected","Accept one; reject rest","Reject all unconfirmed"):
        assert label in block
    assert "SelectionMode.ExtendedSelection" in block
    assert "observation_assertions oa ON oa.observation_id=o.id" in block

def test_observation_workflow_accepts_deferred_state():
    source=Path("src/natureai_next/application/observation_workflow.py").read_text(encoding="utf-8")
    assert '"deferred"' in source
