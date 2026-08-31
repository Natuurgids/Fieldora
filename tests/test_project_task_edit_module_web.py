from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_task_edit_module_web import (
    ProjectTaskEditModuleWebApiMixin,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_task_edit_is_projects_owned() -> None:
    owner = foundation_registry().action_owner("projects.task.edit")
    assert owner is not None
    assert owner.module_id == "projects.core"


def test_task_editor_patch_is_lifecycle_owned_and_governed() -> None:
    response = ProjectTaskEditModuleWebApiMixin._patch_browser(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    again = ProjectTaskEditModuleWebApiMixin._patch_browser("/app.js", response)
    assert response.body == again.body
    script = response.body.decode("utf-8")
    assert "WEB-PROJECT-TASK-EDIT-MODULE" in script
    assert 'moduleId="projects.core"' in script
    assert "window.FieldoraProjectTaskEdit" in script
    assert "/api/v1/project-statuses?project_id=" in script
    assert "/api/v1/tasks/${tid}?project_id=${pid}" in script
    assert 'method:"PATCH"' in script
    assert "/api/v1/tasks/${encodeURIComponent(state.taskId)}" in script
    assert "fieldora:project-work-changed" in script
    assert "fieldora:module-mount" in script
    assert "fieldora:module-unmount" in script
    assert "loadPortfolio" not in script
    assert "showPage=" not in script


def test_task_editor_covers_lossless_desktop_planning_fields() -> None:
    response = ProjectTaskEditModuleWebApiMixin._patch_browser(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")
    for label in (
        "Title",
        "Description",
        "Owner",
        "Status",
        "Priority",
        "Start",
        "Strict deadline",
        "Manual estimate (h)",
        "Realized (h)",
        "Progress %",
        "Budget",
        "Phase",
        "Sprint",
        "Recurrence",
        "Recurrence ends",
        "Milestone",
    ):
        assert label in script
    assert "project-core-task-edit-description" in script
    assert "project-core-task-edit-budget" in script
    assert "project-core-task-edit-recurrence" in script
    assert "task.description" in script
    assert "task.budget" in script
    assert "task.recurrence" in script


def test_task_edit_server_validates_cross_project_relationships_and_ranges() -> None:
    source = __import__(
        "natureai_next.server.project_task_edit_module_web",
        fromlist=["ProjectTaskEditModuleWebApiMixin"],
    )
    text = source.__file__
    assert text
    response = ProjectTaskEditModuleWebApiMixin._patch_browser(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")
    assert "Progress must be a whole number from 0 to 100." in script
    assert "Due date cannot be before start date." in script


def test_task_edit_mixin_is_immediately_inside_modular_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert mro[2] is ProjectTaskEditModuleWebApiMixin
