from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def _project(service: ProjectManagementService) -> str:
    return service.create_project("Hierarchy", actor_id="owner", owner_id="owner")


def test_tasks_are_parent_first_and_creator_is_default_assignee(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite")
    project_id = _project(service)
    parent = service.create_task(project_id, "Parent", actor_id="owner")
    child = service.create_task(project_id, "Child", actor_id="owner", parent_task_id=parent)
    other = service.create_task(project_id, "Other", actor_id="owner")

    tasks = service.tasks(project_id)
    ids = [task.task_id for task in tasks]
    assert ids.index(child) == ids.index(parent) + 1
    assert ids.index(other) > ids.index(child)
    assert next(task for task in tasks if task.task_id == parent).owner_id == "owner"
    assert next(task for task in tasks if task.task_id == child).parent_task_id == parent


def test_task_details_include_description_and_assignee_permissions(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite")
    project_id = _project(service)
    service.set_member_role(project_id, "assignee", "contributor", actor_id="owner")
    task_id = service.create_task(
        project_id,
        "Detailed task",
        actor_id="owner",
        owner_id="assignee",
        description="Full scientific work description",
    )

    assert service.task_details(task_id)["description"] == "Full scientific work description"
    assert service.can_edit_task(task_id, "assignee")
    assert service.can_edit_task(task_id, "owner")


def test_task_notes_are_immediately_queryable_with_user_and_timestamp(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite")
    project_id = _project(service)
    task_id = service.create_task(project_id, "Task", actor_id="owner")
    note_id = service.add_task_note(task_id, "Field note", author_id="owner")

    notes = service.task_notes(task_id)
    assert notes[-1]["note_id"] == note_id
    assert notes[-1]["author_id"] == "owner"
    assert notes[-1]["body"] == "Field note"
    assert int(notes[-1]["created_at_us"]) > 0
