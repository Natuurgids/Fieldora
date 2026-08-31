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
