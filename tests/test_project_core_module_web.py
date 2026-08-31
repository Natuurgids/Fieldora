from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)


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
    assert 'q("project-tree-filter")?.addEventListener("input",renderTree' in script
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
    assert script.rfind("WEB-MODULAR-SHELL: registry-owned navigation bridge") > script.find(
        "WEB-PROJECT-CORE-MODULE"
    )
    assert script.rfind("WEB-MODULAR-SHELL: registry-owned navigation bridge") > script.find(
        "facility-desktop-cockpit"
    )


def test_non_app_script_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_project_core_module_response("/api/v1/status", original) is original
