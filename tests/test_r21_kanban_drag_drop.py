from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def _service(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "science.sqlite")
    project_id = service.create_project("Kanban test", owner_id="admin", actor_id="admin")
    statuses = service.statuses(project_id)
    return service, project_id, statuses


def test_status_update_used_by_kanban_drop_is_persisted_and_audited(tmp_path):
    service, project_id, statuses = _service(tmp_path)
    task_id = service.create_task(
        project_id,
        "Move me",
        actor_id="admin",
        status_id=str(statuses[0]["status_id"]),
    )
    target = str(statuses[1]["status_id"])

    service.update_task(task_id, actor_id="admin", status_id=target)

    task = next(task for task in service.tasks(project_id) if task.task_id == task_id)
    assert task.status_id == target
    events = service.activity(project_id)
    assert any(
        row["event_type"] == "task.updated"
        and row["task_id"] == task_id
        and target in row["details_json"]
        for row in events
    )


def test_subtask_can_move_independently_of_parent(tmp_path):
    service, project_id, statuses = _service(tmp_path)
    source = str(statuses[0]["status_id"])
    target = str(statuses[1]["status_id"])
    parent = service.create_task(project_id, "Parent", actor_id="admin", status_id=source)
    child = service.create_task(
        project_id,
        "Child",
        actor_id="admin",
        status_id=source,
        parent_task_id=parent,
    )

    service.update_task(child, actor_id="admin", status_id=target)

    tasks = {task.task_id: task for task in service.tasks(project_id)}
    assert tasks[parent].status_id == source
    assert tasks[child].status_id == target
    assert tasks[child].parent_task_id == parent


def test_kanban_ui_contains_drag_drop_contract():
    source = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert 'KANBAN_TASK_MIME = "application/x-fieldora-task-id"' in source
    assert "class KanbanTaskList(QListWidget)" in source
    assert "task_dropped = Signal(str, str)" in source
    assert "self._service.update_task(" in source
    assert "status_id=status_id" in source
    assert "Drag tasks or subtasks to another column" in source
