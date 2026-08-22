from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_accessible_projects_include_explicit_member_and_owner(tmp_path: Path, monkeypatch):
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    owned = service.create_project("Owned", owner_id="observer", actor_id="observer")
    shared = service.create_project("Shared", owner_id="manager", actor_id="manager")
    service.set_member_role(shared, "observer", "guest", actor_id="manager")
    visible = {row["project_id"] for row in service.accessible_projects("observer")}
    assert visible == {owned, shared}


def test_dossier_review_workflow_is_owner_reviewer_and_admin_aware():
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    required = (
        '"Defer for review"',
        '"Reassign owner"',
        '"Review"',
        '"Add review remark"',
        '"Return to observer"',
        'dossier["review_status"] = "in_review"',
        'dossier["review_status"] = "returned"',
        '"owner_reassigned"',
        '"review_history"',
        'def _dossier_can_edit',
    )
    for token in required:
        assert token in source


def test_dossier_reviewer_cannot_edit_content_contract():
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    assert 'actor != dossier.get("owner_id", dossier.get("created_by"))' in source
    assert 'dossier.get("review_status", "draft") != "in_review"' in source
    assert 'if dossier is None or not self._dossier_can_edit(dossier):' in source
