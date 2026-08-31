from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_facility_workspace_web import patch_project_facility_workspace_response
from natureai_next.server.project_hierarchy_web import ProjectHierarchyWebApiMixin


def test_project_core_adapter_is_idempotent_and_owns_project_interactions() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_project_core_module_response("/app.js", original)
    patched_again = patch_project_core_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "window.FieldoraProjects" in script
    assert 'moduleId="projects.core"' in script
    assert "fieldora:project-context-changed" in script
    assert 'api("/api/v1/media?limit=500")' in script
    assert 'api(`/api/v1/phases?project_id=${pid}`' in script
    assert 'api(`/api/v1/tasks?project_id=${pid}`' in script
    assert 'api(`/api/v1/sprints?project_id=${pid}`' in script
    assert 'api(`/api/v1/allocations?project_id=${pid}`' in script
    assert 'id="project-core-work-list"' in script
    assert 'data-project-work-kind=' in script
    assert "loadPortfolio=" not in script
    assert 'q("portfolio-scope")' not in script
    assert "showPage=" not in script


def test_final_shell_removes_legacy_project_behavior_but_keeps_cockpit_markup() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    owned = patch_project_core_module_response("/app.js", base)
    legacy = patch_project_facility_workspace_response("/app.js", owned)

    before = legacy.body.decode("utf-8")
    assert "function renderProjectTree()" in before
    assert 'q("portfolio-scope").value=b.dataset.projectScope' in before
    assert 'q("project-tree-filter").oninput=renderProjectTree' in before

    final = patch_modular_shell_response("/app.js", legacy)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "function renderProjectTree()" not in script
    assert "function selectCockpitProject" not in script
    assert 'q("portfolio-scope").value=b.dataset.projectScope' not in script
    assert 'q("project-tree-filter").oninput=renderProjectTree' not in script
    assert "project-desktop-cockpit" in script
    assert "facility-desktop-cockpit" in script
    assert script.rfind("WEB-MODULAR-SHELL: registry-owned navigation bridge") > script.find("WEB-PROJECT-CORE-MODULE")
    assert script.rfind("WEB-MODULAR-SHELL: registry-owned navigation bridge") > script.find("facility-desktop-cockpit")


def test_final_shell_retires_old_hierarchy_browser_patch_when_project_owner_exists() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy_hierarchy = ProjectHierarchyWebApiMixin._patch_project_hierarchy_response("/app.js", base)
    assert "WEB-032: contextual Project hierarchy creation" in legacy_hierarchy.body.decode("utf-8")

    owned = patch_project_core_module_response("/app.js", legacy_hierarchy)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "WEB-032: contextual Project hierarchy creation" not in script
    assert "const priorLoadPortfolio=loadPortfolio" not in script
    assert 'id="project-core-work-list"' in script


def test_projects_work_surface_uses_governed_hierarchy_apis_not_portfolio_data() -> None:
    patched = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "state={mounted:false" in script
    assert "phases:[],tasks:[],sprints:[],allocations:[]" in script
    assert "Promise.all([" in script
    assert "/api/v1/phases?project_id=" in script
    assert "/api/v1/tasks?project_id=" in script
    assert "/api/v1/sprints?project_id=" in script
    assert "/api/v1/allocations?project_id=" in script
    assert "JSON.parse(q(\"portfolio-list\")" not in script
    assert "data-project-work-kind" in script


def test_non_app_script_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_project_core_module_response("/api/v1/status", original) is original
