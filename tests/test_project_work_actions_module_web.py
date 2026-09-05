from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_hierarchy_web import ProjectHierarchyWebApiMixin
from natureai_next.server.project_work_actions_module_web import (
    ProjectWorkActionsModuleWebApiMixin,
    patch_project_work_actions_module_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_projects_core_owns_work_creation_actions() -> None:
    registry = foundation_registry()

    for action in (
        "projects.phase.create",
        "projects.task.create",
        "projects.milestone.create",
        "projects.subtask.create",
        "projects.sprint.create",
        "projects.allocation.create",
    ):
        owner = registry.action_owner(action)
        assert owner is not None
        assert owner.module_id == "projects.core"


def test_work_actions_adapter_is_idempotent_and_module_owned() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")

    patched = patch_project_work_actions_module_response("/app.js", original)
    patched_again = patch_project_work_actions_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert "window.FieldoraProjectWorkActions" in script
    assert 'moduleId="projects.core"' in script
    assert 'data-project-work-create="phase"' in script
    assert 'data-project-work-create="subtask"' in script
    assert "showPage=" not in script
    assert "loadPortfolio=" not in script


def test_work_actions_use_governed_hierarchy_apis_and_visible_validation() -> None:
    patched = patch_project_work_actions_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'path="/api/v1/phases"' in script
    assert 'path="/api/v1/tasks"' in script
    assert 'path="/api/v1/sprints"' in script
    assert 'path="/api/v1/allocations"' in script
    assert "Phase name is required." in script
    assert "Task title is required." in script
    assert "User and start date are required." in script
    assert "Allocation must be between 0 and 100 percent." in script
    assert "Sprint end date must not be before start date." in script
    assert "fieldora:project-work-changed" in script


def test_capability_projection_only_controls_browser_discoverability() -> None:
    patched = patch_project_work_actions_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "/capabilities" in script
    assert "fieldoraAuthorizationHidden" in script
    assert "caps?.actions?.edit===true" in script
    # The browser still calls the governed POST endpoints; authorization is
    # independently enforced by ProjectHierarchyWebApiMixin on the server.
    assert 'method:"POST",purpose:"research"' in script


def test_final_shell_keeps_new_actions_and_retires_old_hierarchy_browser_owner() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = ProjectHierarchyWebApiMixin._patch_project_hierarchy_response("/app.js", base)
    core = patch_project_core_module_response("/app.js", legacy)
    actions = patch_project_work_actions_module_response("/app.js", core)

    final = patch_modular_shell_response("/app.js", actions)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert "WEB-032: contextual Project hierarchy creation" not in script
    assert "const priorLoadPortfolio=loadPortfolio" not in script
    assert 'data-project-work-create="phase"' in script
    assert 'id="project-core-work-list"' in script


def test_work_actions_mixin_is_composed_before_project_core_adapter() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert ProjectWorkActionsModuleWebApiMixin in mro
    project_core = next(base for base in mro if base.__name__ == "ProjectCoreModuleWebApiMixin")
    assert mro.index(ProjectWorkActionsModuleWebApiMixin) < mro.index(project_core)


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_project_work_actions_module_response("/api/v1/status", original) is original
