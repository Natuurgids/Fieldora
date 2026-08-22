from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_phase_sprint_and_estimate_rollups(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "project.db")
    project_id = service.create_project("Survey", owner_id="leader", actor_id="leader")
    phase_id = service.create_phase(project_id, "Fieldwork", actor_id="leader", planned_budget=1200)
    sprint_id = service.create_sprint(
        project_id, "Sprint 1", actor_id="leader", start_date="2026-08-01", end_date="2026-08-14"
    )
    task_id = service.create_task(
        project_id, "Capture", actor_id="leader", phase_id=phase_id, sprint_id=sprint_id,
        estimate_hours=100, realized_hours=30,
    )
    service.create_task(
        project_id, "Site A", actor_id="leader", parent_task_id=task_id,
        estimate_hours=12, realized_hours=8,
    )
    service.create_task(
        project_id, "Site B", actor_id="leader", parent_task_id=task_id,
        estimate_hours=16, realized_hours=10,
    )
    task = next(row for row in service.tasks(project_id) if row.task_id == task_id)
    assert task.phase_name == "Fieldwork"
    assert task.sprint_name == "Sprint 1"
    assert task.manual_estimate_hours == 100
    assert task.calculated_estimate_hours == 28
    assert task.effective_estimate_hours == 28
    assert task.realized_hours == 18
    phase = service.phases(project_id)[0]
    assert phase["calculated_estimate_hours"] == 28
    assert phase["calculated_realized_hours"] == 18


def test_drag_assignment_moves_task_and_subtasks_to_phase(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "project.db")
    project_id = service.create_project("Survey", owner_id="leader", actor_id="leader")
    first = service.create_phase(project_id, "Preparation", actor_id="leader")
    second = service.create_phase(project_id, "Fieldwork", actor_id="leader")
    task_id = service.create_task(project_id, "Prepare", actor_id="leader", phase_id=first)
    child_id = service.create_task(project_id, "Check equipment", actor_id="leader", parent_task_id=task_id)
    service.assign_task_phase(task_id, second, actor_id="leader")
    rows = {row.task_id: row for row in service.tasks(project_id)}
    assert rows[task_id].phase_id == second
    assert rows[child_id].phase_id == second


def test_sprint_is_persisted_as_master_data(tmp_path: Path) -> None:
    database = tmp_path / "project.db"
    service = ProjectManagementService(database)
    project_id = service.create_project("Survey", owner_id="leader", actor_id="leader")
    sprint_id = service.create_sprint(project_id, "August", actor_id="leader")
    task_id = service.create_task(project_id, "Task", actor_id="leader", sprint_id=sprint_id)
    reopened = ProjectManagementService(database)
    task = next(row for row in reopened.tasks(project_id) if row.task_id == task_id)
    assert task.sprint_id == sprint_id
    assert task.sprint_name == "August"
