from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_project_workspace_uses_parent_first_tree_and_permission_safe_tabs() -> None:
    source = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert "self._task_tree = PhaseTaskTree()" in source
    assert 'self._detail_tabs.addTab(self._overview, "Overview")' in source
    for tab in ("Discussion", "Subtasks", "Evidence", "Files", "Notes", "Time", "Dependencies", "Activity"):
        assert f'"{tab}"' in source
    task_page = source[source.index("def _build_tasks_page"):source.index("def _build_board_page")]
    assert '"Audit"' not in task_page
    assert '"Security"' not in task_page
    assert "Parent task" in source


def test_parent_subtask_order_time_and_dependency_details(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project = service.create_project("Project", owner_id="lead", actor_id="lead")
    statuses = {row["category"]: row["status_id"] for row in service.statuses(project)}
    parent = service.create_task(project, "Parent", actor_id="lead", status_id=statuses["todo"])
    child = service.create_task(
        project, "Child", actor_id="lead", status_id=statuses["active"], parent_task_id=parent
    )
    other = service.create_task(project, "Dependency", actor_id="lead", status_id=statuses["todo"])
    service.add_dependency(child, other, actor_id="lead")
    service.log_time(child, "lead", 75, note="Field work")

    ordered = service.tasks(project)
    ids = [row.task_id for row in ordered]
    assert ids.index(child) == ids.index(parent) + 1
    assert service.dependencies(child)[0]["task_id"] == other
    assert service.time_entries(child)[0]["minutes"] == 75
    assert service.task_activity(child)


def test_library_is_unified_and_double_click_opens_exact_asset() -> None:
    v5 = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    library = v5[v5.index("class Library(Page):"):v5.index("class Observations(Page):")]
    for kind in ("Photos", "Sounds", "Videos", "Documents", "Maps / GIS", "Other media"):
        assert kind in library
    assert "itemDoubleClicked.connect" in library
    assert "__asset_open__" in library
    assert "photo_assets" in library
    assert "sound_assets" in library
    assert "video_assets" in library
    assert "document_assets" in library

    application = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert 'if target is not None and hasattr(target, "select_asset")' in application
    assert '"image": "Photos"' in application

    photo_library = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    media_library = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "def select_asset(self, asset_id: str) -> bool:" in photo_library
    assert "def select_asset(self, asset_id: str) -> bool:" in media_library


def test_ai_batch_progress_windows_are_non_modal_and_not_parent_pinned() -> None:
    progress = Path("src/natureai_next/ui/qt/capability_execution.py").read_text(encoding="utf-8")
    assert "super().__init__(None)" in progress
    assert "Qt.WindowModality.NonModal" in progress
    assert "Qt.WindowType.WindowMinimizeButtonHint" in progress
    for source_name in ("library.py", "media_library.py"):
        source = Path(f"src/natureai_next/ui/qt/{source_name}").read_text(encoding="utf-8")
        assert "CapabilityBatchProgressDialog(" in source
        assert "parent=None" in source
