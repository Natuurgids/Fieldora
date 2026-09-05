from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_progress_module_web import (
    ProjectProgressModuleWebApiMixin,
    patch_project_progress_module_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_progress_adapter_is_idempotent_and_projects_owned() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_project_progress_module_response("/app.js", original)
    again = patch_project_progress_module_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-PROGRESS-MODULE" in script
    assert 'moduleId="projects.core"' in script
    assert 'id="project-core-progress"' in script
    assert "window.FieldoraProjectProgress" in script
    assert "fieldora:project-context-changed" in script
    assert "fieldora:project-work-changed" in script
    assert "fieldora:project-lifecycle-changed" in script
    assert "loadPortfolio" not in script
    assert "showPage=" not in script


def test_progress_projection_uses_governed_project_task_and_status_apis() -> None:
    patched = patch_project_progress_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'api("/api/v1/projects",{purpose:"research"})' in script
    assert "api(`/api/v1/tasks?project_id=${encoded}`" in script
    assert "api(`/api/v1/project-statuses?project_id=${encoded}`" in script
    assert "Average task progress" in script
    assert "Blocked tasks" in script
    assert "Overdue tasks" in script
    assert "Milestones complete" in script
    assert "Realized / estimated effort" in script
    assert "task.status_category" in script
    assert "task.progress" in script
    assert "task.effective_estimate_hours??task.estimate_hours??task.manual_estimate" in script
    assert "task.realized_hours??task.realized??task.actual_hours" in script


def test_kanban_moves_are_capability_aware_and_use_authorized_task_patch() -> None:
    patched = patch_project_progress_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'data-project-planning-view="kanban"' in script
    assert 'data-project-kanban-drop="${esc(id)}"' in script
    assert 'data-project-kanban-status="${esc(task.id)}"' in script
    assert "/capabilities`" in script
    assert "caps?.actions?.edit===true" in script
    assert "if(!state.canEdit||!taskId||!statusId)return" in script
    assert "api(`/api/v1/tasks/${encodeURIComponent(taskId)}`" in script
    assert 'method:"PATCH"' in script
    assert "JSON.stringify({project_id:state.projectId,status_id:statusId})" in script
    assert "text/x-fieldora-task-id" in script
    assert "fieldora:project-work-changed" in script
    success = script.split('async function moveTask(taskId,statusId){', 1)[1].split(
        '}catch(error)', 1
    )[0]
    assert "await refresh()" not in success
    assert 'catch(error){emitError(error,"Task status could not be changed.");await refresh()}' in script


def test_gantt_matches_desktop_date_fallback_and_opens_task_editor() -> None:
    patched = patch_project_progress_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'data-project-planning-view="gantt"' in script
    assert "task.start_date||task.due_date" in script
    assert "task.due_date||task.start_date" in script
    assert "end:Math.max(a,b)" in script
    assert "Add task dates to build the Gantt timeline." in script
    assert "taskProgress(row.task)" in script
    assert "isBlocked(row.task)" in script
    assert "isDone(row.task)" in script
    assert "fieldora:project-task-edit-request" in script


def test_projects_contract_owns_progress_and_planning_actions() -> None:
    registry = foundation_registry()
    for action in (
        "projects.progress.refresh",
        "projects.planning.view.select",
        "projects.task.status.move",
        "projects.gantt.inspect",
    ):
        owner = registry.action_owner(action)
        assert owner is not None
        assert owner.module_id == "projects.core"


def test_progress_mixin_is_composed_inside_modular_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert ProjectProgressModuleWebApiMixin in mro[2:]


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_project_progress_module_response("/api/v1/projects", original) is original
