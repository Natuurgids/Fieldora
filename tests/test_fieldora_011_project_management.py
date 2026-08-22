from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from natureai_next.application.project_management import ProjectManagementService


def _project(service: ProjectManagementService) -> tuple[str, dict[str, str]]:
    project_id = service.create_project(
        "Coastal survey",
        owner_id="lead",
        actor_id="lead",
        start_date="2026-08-01",
        due_date="2026-09-30",
        budget=20_000,
    )
    statuses = {
        row["category"]: row["status_id"] for row in service.statuses(project_id)
    }
    return project_id, statuses


def test_tasks_subtasks_dependencies_mentions_and_audit(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id, statuses = _project(service)
    foundation = service.create_task(
        project_id,
        "Prepare samples",
        actor_id="lead",
        owner_id="lead",
        status_id=statuses["todo"],
        priority="critical",
        estimate_hours=8,
    )
    analysis = service.create_task(
        project_id,
        "Analyse samples",
        actor_id="lead",
        owner_id="analyst",
        parent_task_id=foundation,
        status_id=statuses["todo"],
        estimate_hours=16,
    )
    service.add_dependency(analysis, foundation, actor_id="lead")
    service.add_checklist_item(foundation, "Label every vial", actor_id="lead")
    service.add_comment(foundation, "Please verify this @analyst", author_id="lead")
    service.log_time(foundation, "lead", 90, note="Preparation")

    tasks = {task.task_id: task for task in service.tasks(project_id)}
    assert tasks[analysis].blocked is True
    assert tasks[analysis].parent_task_id == foundation
    assert service.comments(foundation)[0]["mentions_json"] == '["analyst"]'
    assert any(row["kind"] == "comment.mentioned" for row in service.notifications("analyst"))
    assert service.dashboard(project_id)["actual_hours"] == 1.5
    assert len(service.activity(project_id)) >= 7


def test_rbac_capacity_recurring_templates_and_exports(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id, statuses = _project(service)
    service.set_member_role(project_id, "guest", "guest", actor_id="lead")
    service.set_capacity(project_id, "lead", 32, 75, actor_id="lead")
    service.add_leave("lead", "2026-08-10", "2026-08-12", "PTO")
    field_id = service.add_custom_field(
        project_id, "Cost code", "text", actor_id="lead"
    )
    recurring = service.create_task(
        project_id,
        "Weekly review",
        actor_id="lead",
        status_id=statuses["todo"],
        recurrence="weekly",
        due_date="2026-07-01",
    )
    service.set_custom_field_value(
        recurring, field_id, "BIO-2026", actor_id="lead"
    )
    assert service.custom_field_values(recurring)[0]["value_json"] == '"BIO-2026"'

    with pytest.raises(PermissionError):
        service.create_task(project_id, "Forbidden", actor_id="guest")

    assert service.materialize_recurring_tasks(project_id, actor_id="lead")
    template_id = service.save_template(project_id, "Survey", actor_id="lead")
    second = service.create_project(
        "Second survey", owner_id="lead", actor_id="lead", template_id=template_id
    )
    assert service.tasks(second)
    csv_path = tmp_path / "tasks.csv"
    service.export_csv(project_id, csv_path)
    assert "Weekly review" in csv_path.read_text(encoding="utf-8")
    workbook = service.export_xlsx(project_id, tmp_path / "tasks.xlsx")
    assert ZipFile(workbook).testzip() is None
    assert "Coastal survey" in service.report_html(project_id)
    portal = service.client_portal_snapshot(project_id)
    assert "comments" not in portal
    assert "health" in portal


def test_science_route_uses_replacement_workspace() -> None:
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    ui = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert '"projects": (self._project_management_page' in source
    for feature in (
        "Kanban",
        "Grid",
        "Gantt",
        "Calendar",
        "Workload & Time",
        "Dashboard",
        "Activity",
        "Project Settings",
    ):
        assert feature in ui


def test_subtasks_are_grouped_directly_under_parent(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id, statuses = _project(service)
    first_parent = service.create_task(
        project_id, "First parent", actor_id="lead", status_id=statuses["todo"]
    )
    second_parent = service.create_task(
        project_id, "Second parent", actor_id="lead", status_id=statuses["todo"]
    )
    child = service.create_task(
        project_id, "Child entered last", actor_id="lead",
        parent_task_id=first_parent, status_id=statuses["active"]
    )
    grandchild = service.create_task(
        project_id, "Grandchild", actor_id="lead",
        parent_task_id=child, status_id=statuses["done"]
    )

    ordered = service.tasks(project_id)
    ids = [task.task_id for task in ordered]
    assert ids.index(child) == ids.index(first_parent) + 1
    assert ids.index(grandchild) == ids.index(child) + 1
    assert ids.index(second_parent) > ids.index(grandchild)


def test_subtask_parent_must_belong_to_same_project(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    first, first_statuses = _project(service)
    second = service.create_project("Other", owner_id="lead", actor_id="lead")
    parent = service.create_task(
        first, "Parent", actor_id="lead", status_id=first_statuses["todo"]
    )
    with pytest.raises(ValueError, match="parent task does not belong"):
        service.create_task(second, "Invalid child", actor_id="lead", parent_task_id=parent)
