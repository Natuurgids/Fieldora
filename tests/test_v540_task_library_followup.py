from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_task_defaults_to_creator_and_assignee_can_edit_and_note(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id = service.create_project("Test", owner_id="owner", actor_id="owner")
    status = service.statuses(project_id)[0]["status_id"]
    task_id = service.create_task(project_id, "Assigned by default", actor_id="owner", status_id=status)
    task = next(row for row in service.tasks(project_id) if row.task_id == task_id)
    assert task.owner_id == "owner"

    service.update_task(task_id, actor_id="owner", description="Editable")
    note_id = service.add_task_note(task_id, "First note", author_id="owner")
    notes = service.task_notes(task_id)
    assert notes[0]["note_id"] == note_id
    assert notes[0]["author_id"] == "owner"
    assert notes[0]["body"] == "First note"


def test_task_workspace_contract_and_library_routes() -> None:
    project_ui = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    library_ui = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "itemDoubleClicked.connect" in project_ui
    assert "def _edit_task" in project_ui
    assert "def _save_task_note" in project_ui
    assert "My assigned tasks and activities" in project_ui
    assert "Whole project calendar" in project_ui
    task_toolbar = project_ui[project_ui.index("task_actions = QHBoxLayout()") : project_ui.index("left = QWidget()")]
    assert '("New subtask", self._new_subtask)' not in task_toolbar
    for route in ("('Photos','Photos')", "('Sounds','Sounds')", "('Videos','Videos')", "('Documents','Documents')"):
        assert route in library_ui
    assert 'AssetCatalogService' in library_ui
