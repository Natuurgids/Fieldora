from __future__ import annotations

from natureai_next.application.project_management import ProjectManagementService
from natureai_next.application.project_task_detail import ProjectTaskDetailQuery


def test_task_detail_preserves_editable_desktop_fields(tmp_path) -> None:
    database = tmp_path / "projects.sqlite3"
    service = ProjectManagementService(database)
    project_id = service.create_project(
        "Wetland survey",
        actor_id="researcher",
        owner_id="researcher",
    )
    status_id = service.statuses(project_id)[1]["status_id"]
    task_id = service.create_task(
        project_id,
        "Review transects",
        actor_id="researcher",
        owner_id="researcher",
        status_id=str(status_id),
        description="Compare spring and summer evidence.",
        priority="high",
        start_date="2026-08-01",
        due_date="2026-09-15",
        estimate_hours=12.5,
        budget=450.0,
        recurrence="weekly",
        recurrence_end="2026-10-01",
        milestone=True,
        realized_hours=3.25,
    )
    service.update_task(task_id, actor_id="researcher", progress=35)

    item = ProjectTaskDetailQuery(database).get(project_id, task_id)

    assert item is not None
    assert item["id"] == task_id
    assert item["description"] == "Compare spring and summer evidence."
    assert item["priority"] == "high"
    assert item["estimate_hours"] == 12.5
    assert item["realized_hours"] == 3.25
    assert item["budget"] == 450.0
    assert item["progress"] == 35
    assert item["recurrence"] == "weekly"
    assert item["recurrence_end"] == "2026-10-01"
    assert item["milestone"] is True


def test_task_detail_is_scoped_to_project(tmp_path) -> None:
    database = tmp_path / "projects.sqlite3"
    service = ProjectManagementService(database)
    first = service.create_project("First", actor_id="researcher", owner_id="researcher")
    second = service.create_project("Second", actor_id="researcher", owner_id="researcher")
    task_id = service.create_task(first, "Scoped", actor_id="researcher")

    assert ProjectTaskDetailQuery(database).get(second, task_id) is None
