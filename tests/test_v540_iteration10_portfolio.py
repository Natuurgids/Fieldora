from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_portfolio_only_contains_accessible_projects_and_rolls_up_tasks(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    first = service.create_project("Project One", owner_id="manager", actor_id="manager", budget=1000)
    second = service.create_project("Project Two", owner_id="other", actor_id="other", budget=2000)
    service.set_member_role(second, "manager", "manager", actor_id="other")
    hidden = service.create_project("Hidden", owner_id="hidden-owner", actor_id="hidden-owner")

    phase = service.create_phase(first, "Planning", actor_id="manager", planned_budget=500, realized_budget=125)
    parent = service.create_task(first, "Plan survey", actor_id="manager", phase_id=phase, estimate_hours=40)
    service.create_task(first, "Prepare protocol", actor_id="manager", parent_task_id=parent, phase_id=phase, estimate_hours=12)
    service.create_task(first, "Book vessel", actor_id="manager", parent_task_id=parent, phase_id=phase, estimate_hours=8)
    service.create_task(second, "Second project task", actor_id="manager", estimate_hours=10)

    snapshot = service.portfolio_snapshot("manager")
    names = {row["name"] for row in snapshot["projects"]}
    assert names == {"Project One", "Project Two"}
    assert "Hidden" not in names
    assert snapshot["summary"]["project_count"] == 2
    assert snapshot["summary"]["task_count"] == 4
    first_row = next(row for row in snapshot["projects"] if row["project_id"] == first)
    assert first_row["effective_estimate_hours"] == 20
    assert first_row["realized_budget"] == 125
    assert first_row["budget_variance"] == 875


def test_platform_administrator_portfolio_sees_all_projects(tmp_path: Path, monkeypatch) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    service.create_project("One", owner_id="one", actor_id="one")
    service.create_project("Two", owner_id="two", actor_id="two")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    snapshot = service.portfolio_snapshot("admin")
    assert {row["name"] for row in snapshot["projects"]} == {"One", "Two"}
