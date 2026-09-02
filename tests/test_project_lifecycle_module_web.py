from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_lifecycle_module_web import (
    ProjectLifecycleModuleWebApiMixin,
    patch_project_lifecycle_module_response,
)
from natureai_next.server.project_lifecycle_web import patch_project_lifecycle_response
from natureai_next.server.web_module_contracts import foundation_registry


def test_projects_core_owns_lifecycle_actions() -> None:
    registry = foundation_registry()

    for action in (
        "projects.details.edit",
        "projects.status.change",
        "projects.archive",
    ):
        owner = registry.action_owner(action)
        assert owner is not None
        assert owner.module_id == "projects.core"


def test_lifecycle_adapter_is_idempotent_and_does_not_depend_on_portfolio() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")

    patched = patch_project_lifecycle_module_response("/app.js", original)
    patched_again = patch_project_lifecycle_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-LIFECYCLE-MODULE" in script
    assert "window.FieldoraProjectLifecycle" in script
    assert 'moduleId="projects.core"' in script
    assert "loadPortfolio" not in script
    assert "portfolio-project-lifecycle" not in script
    assert "showPage=" not in script


def test_lifecycle_reselection_uses_project_context_contract() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert "if(focusId&&context?.select)await context.select(focusId)" in script
    assert "window.FieldoraProjects?.selectProject" not in script


def test_lifecycle_mount_reads_current_project_through_context_contract() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'state.projectId=projectContext()?.current?.()||""' in script
    assert "window.FieldoraProjects?.currentProject" not in script


def test_lifecycle_adapter_keeps_revision_conflict_and_visible_validation() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "expected_revision:project.revision" in script
    assert "revision_conflict" in script
    assert "Latest values reloaded" in script
    assert "Project name is required." in script
    assert "Budget must be zero or greater." in script
    assert "Due date must not be before start date." in script
    assert '/status`' in script
    assert '/archive`' in script
    assert "fieldora:project-lifecycle-changed" in script


def test_lifecycle_capability_projection_is_not_server_authorization() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "/capabilities" in script
    assert "fieldoraAuthorizationHidden" in script
    assert "caps?.actions?.edit===true" in script
    assert 'method:"PATCH",purpose:"research"' in script


def test_final_shell_retires_old_lifecycle_browser_patch_only_when_owner_exists() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = patch_project_lifecycle_response("/app.js", base)
    assert "Fieldora Project lifecycle: selected-project edit" in legacy.body.decode("utf-8")

    without_owner = patch_modular_shell_response("/app.js", legacy)
    assert "Fieldora Project lifecycle: selected-project edit" in without_owner.body.decode("utf-8")

    owned = patch_project_lifecycle_module_response("/app.js", legacy)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-LIFECYCLE-MODULE" in script
    assert "Fieldora Project lifecycle: selected-project edit" not in script
    assert "portfolio-project-lifecycle-editor" not in script
    assert "project-core-lifecycle-editor" in script


def test_lifecycle_module_is_composed_before_legacy_transport_mixin() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert ProjectLifecycleModuleWebApiMixin in mro
    assert mro.index(ProjectLifecycleModuleWebApiMixin) < mro.index(
        next(base for base in mro if base.__name__ == "ProjectLifecycleWebApiMixin")
    )


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_project_lifecycle_module_response("/api/v1/status", original) is original
