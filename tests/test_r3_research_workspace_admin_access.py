from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_authenticated_platform_admin_can_see_and_edit_all_projects(tmp_path: Path, monkeypatch):
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    project_id = service.create_project("Research project", owner_id="owner", actor_id="owner")

    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")

    projects = service.accessible_projects("admin")
    assert [row["project_id"] for row in projects] == [project_id]
    assert service.can(project_id, "admin", "view")
    assert service.can(project_id, "admin", "create")
    assert service.can(project_id, "admin", "edit")
    assert service.can(project_id, "admin", "manage")


def test_non_member_non_admin_cannot_see_project(tmp_path: Path, monkeypatch):
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    service.create_project("Research project", owner_id="owner", actor_id="owner")

    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "viewer")

    assert service.accessible_projects("viewer") == ()
