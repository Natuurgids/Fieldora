from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.capacity_module_web import (
    CapacityModuleWebApiMixin,
    patch_capacity_module_response,
)
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_capacity_integration_web import (
    ProjectCapacityIntegrationWebApiMixin,
    patch_project_capacity_integration_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_capacity_owns_project_integration_actions() -> None:
    registry = foundation_registry()
    capacity = registry.action_owner("capacity.project.open")
    allocations = registry.action_owner("capacity.project.allocations.view")

    assert capacity is not None
    assert allocations is capacity
    assert capacity.module_id == "capacity"
    assert capacity.dependencies == ()
    assert capacity.requires_contracts == (
        "projects.context.select",
        "projects.toolbar.extend",
    )


def test_capacity_module_is_idempotent_and_reads_governed_project_allocations() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_capacity_module_response("/app.js", original)
    again = patch_capacity_module_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-CAPACITY-MODULE" in script
    assert "window.FieldoraCapacity=Object.freeze" in script
    assert "async function openProject(projectId)" in script
    assert "/api/v1/allocations?project_id=${encodeURIComponent(state.projectId)}" in script
    assert 'purpose:"research"' in script
    assert 'data-fieldora-action="capacity.project.allocations.view"' in script
    assert "fieldora:capacity-project-changed" in script
    assert "work-schedules" not in script
    assert "absences" not in script
    assert "obligations" not in script


def test_project_capacity_adapter_uses_replaceable_projects_contracts() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_project_capacity_integration_response("/app.js", original)
    again = patch_project_capacity_integration_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-CAPACITY-INTEGRATION" in script
    assert 'ownerModule="capacity"' in script
    assert 'entryKey="capacity.project.open"' in script
    assert 'navigate?.("/capacity","project-capacity-integration","push")' in script
    assert 'resolve?.("projects.context.select")' in script
    assert 'resolve?.("projects.toolbar.extend")' in script
    assert "projectContext()?.current?.()" in script
    assert "toolbar.upsert" in script
    assert 'action:"capacity.project.open"' in script
    assert 'event.detail?.contract' in script
    assert "project-desktop-cockpit" not in script
    assert "cockpit-toolbar" not in script
    assert 'projectModule="projects.core"' not in script
    assert 'module_id===projectModule' not in script
    assert "window.FieldoraProjects" not in script
    assert "window.FieldoraCapacity" in script
    assert 'q("capacity-project")' in script
    assert "syncLegacyProjectSelector()" in script
    assert 'resolve?.("projects.list.read")' not in script
    assert "projects[0]" not in script
    assert "loadCapacity" not in script


def test_capacity_integration_is_composed_inside_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert ProjectCapacityIntegrationWebApiMixin in mro[2:]
    assert CapacityModuleWebApiMixin in mro[2:]
    assert mro.index(ProjectCapacityIntegrationWebApiMixin) < mro.index(
        CapacityModuleWebApiMixin
    )


def test_non_app_responses_are_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_capacity_module_response("/api/v1/allocations", original) is original
    assert (
        patch_project_capacity_integration_response("/api/v1/projects", original)
        is original
    )
