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


def test_progress_projection_uses_governed_project_and_task_apis() -> None:
    patched = patch_project_progress_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'api("/api/v1/projects",{purpose:"research"})' in script
    assert "api(`/api/v1/tasks?project_id=${encoded}`" in script
    assert "Average task progress" in script
    assert "Blocked tasks" in script
    assert "Overdue tasks" in script
    assert "Milestones complete" in script
    assert "Realized / estimated effort" in script
    assert "task.status_category" in script
    assert "task.progress" in script


def test_projects_contract_owns_progress_refresh() -> None:
    owner = foundation_registry().action_owner("projects.progress.refresh")
    assert owner is not None
    assert owner.module_id == "projects.core"


def test_progress_mixin_is_immediately_inside_modular_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert mro[2] is ProjectProgressModuleWebApiMixin


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_project_progress_module_response("/api/v1/projects", original) is original
