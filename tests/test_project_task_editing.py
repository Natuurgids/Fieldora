from __future__ import annotations

from natureai_next.application.project_management import ProjectManagementService
from natureai_next.server.api import ApiResponse
from natureai_next.server.project_task_edit_module_web import ProjectTaskEditModuleWebApiMixin
from natureai_next.server.project_task_editing import (
    ProjectTaskEditingFacade,
    wrap_project_task_editing,
)


def test_local_task_editing_facade_preserves_full_task_detail(tmp_path) -> None:
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project_id = service.create_project(
        "Wetland survey", actor_id="researcher", owner_id="researcher"
    )
    phase_id = service.create_phase(project_id, "Fieldwork", actor_id="researcher")
    sprint_id = service.create_sprint(project_id, "Spring", actor_id="researcher")
    task_id = service.create_task(
        project_id,
        "Review transects",
        actor_id="researcher",
        description="Original detail",
        budget=125.0,
        recurrence="weekly",
        phase_id=phase_id,
        sprint_id=sprint_id,
    )
    facade = wrap_project_task_editing(service)

    assert isinstance(facade, ProjectTaskEditingFacade)
    assert phase_id in facade.phase_ids(project_id)
    assert sprint_id in facade.sprint_ids(project_id)

    facade.update_task(
        task_id,
        actor_id="researcher",
        description="Updated detail",
        budget=250.0,
        recurrence="monthly",
        progress=40,
    )
    item = facade.task_detail(project_id, task_id)

    assert item is not None
    assert item["description"] == "Updated detail"
    assert item["budget"] == 250.0
    assert item["recurrence"] == "monthly"
    assert item["progress"] == 40


def test_local_task_summary_contract_remains_native(tmp_path) -> None:
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project_id = service.create_project(
        "Forest plots", actor_id="researcher", owner_id="researcher"
    )
    service.create_task(project_id, "Measure plots", actor_id="researcher")
    facade = wrap_project_task_editing(service)

    tasks = facade.tasks(project_id)

    assert len(tasks) == 1
    assert tasks[0].title == "Measure plots"
    assert tasks[0].status_id


class _ManagedCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self):
        return list(self.rows)


class _ManagedConnection:
    def __init__(self, cursor: _ManagedCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self) -> _ManagedCursor:
        return self._cursor


class _ManagedTaskDelegate:
    def __init__(self) -> None:
        self.cursor = _ManagedCursor(
            [
                (
                    "task-1",
                    "project-1",
                    None,
                    "Review samples",
                    "Rich task detail",
                    "status-blocked",
                    "Blocked",
                    "blocked",
                    "researcher",
                    "high",
                    "2026-09-01",
                    "2026-09-04",
                    12.5,
                    4.25,
                    35,
                    80.0,
                    "weekly",
                    "2026-10-01",
                    False,
                    3,
                    "phase-1",
                    "Fieldwork",
                    "sprint-1",
                    "Autumn sprint",
                    True,
                )
            ]
        )

    def _connect(self) -> _ManagedConnection:
        return _ManagedConnection(self.cursor)


def test_managed_task_list_exposes_desktop_planning_fidelity() -> None:
    delegate = _ManagedTaskDelegate()
    facade = ProjectTaskEditingFacade(delegate)

    tasks = facade.tasks("org-1")

    assert delegate.cursor.params == ("org-1",)
    assert "s.category='blocked'" in delegate.cursor.query
    assert len(tasks) == 1
    task = tasks[0]
    assert task["status_id"] == "status-blocked"
    assert task["status_name"] == "Blocked"
    assert task["status_category"] == "blocked"
    assert task["progress"] == 35
    assert task["blocked"] is True
    assert task["owner_id"] == "researcher"
    assert task["assignee_id"] == "researcher"
    assert task["estimate_hours"] == 12.5
    assert task["manual_estimate"] == 12.5
    assert task["effective_estimate_hours"] == 12.5
    assert task["realized_hours"] == 4.25
    assert task["actual_hours"] == 4.25
    assert task["phase_name"] == "Fieldwork"
    assert task["sprint_name"] == "Autumn sprint"
    assert task["recurrence"] == "weekly"
    assert task["budget"] == 80.0


def test_task_edit_wrapper_is_idempotent(tmp_path) -> None:
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    facade = wrap_project_task_editing(service)
    assert wrap_project_task_editing(facade) is facade


class _DownstreamApi:
    def __init__(self) -> None:
        self.session_wraps = 0

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        return ApiResponse.json(200, {"downstream": target})

    def _browser_session_response(self, *args):
        self.session_wraps += 1
        return args[-1]


class _TaskEditHarness(ProjectTaskEditModuleWebApiMixin, _DownstreamApi):
    pass


def test_task_edit_mixin_does_not_wrap_unowned_api_routes() -> None:
    api = _TaskEditHarness()
    response = api.dispatch("GET", "/api/v1/unrelated", {}, b"")

    assert response.status == 200
    assert api.session_wraps == 0
