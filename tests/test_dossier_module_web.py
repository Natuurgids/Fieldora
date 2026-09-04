from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_module_web import patch_dossier_module_response


def test_dossier_module_is_idempotent_and_owns_workspace_behavior() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_dossier_module_response("/app.js", original)
    again = patch_dossier_module_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-DOSSIER-MODULE" in script
    assert 'const moduleId="dossiers.workspace"' in script
    assert "window.FieldoraDossiers=Object.freeze" in script
    assert 'q("page-dossiers")' in script
    assert 'q("dossier-refresh")?.addEventListener("click",refresh' in script
    assert 'q("dossier-save")?.addEventListener("click",save' in script
    assert 'q("dossier-workspace-list")?.addEventListener("click"' in script
    assert 'api("/api/v1/dossiers")' in script
    assert 'api("/api/v1/dossier-reviews")' in script
    assert 'fieldora:dossier-workspace-changed' in script


def test_dossier_module_uses_only_canonical_project_context_and_fails_closed() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert 'function currentProject(){return String(context()?.current?.()||"")}' in script
    assert 'Select a Project before creating a dossier.' in script
    assert 'project_id:projectId' in script
    assert 'resolve?.("projects.list.read")' not in script
    assert "projects[0]" not in script
    assert "state.projectId||" not in script


def test_dossier_module_tracks_context_lifecycle_without_project_module_dependency() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")

    assert 'document.addEventListener("fieldora:project-context-changed"' in script
    assert 'event.detail?.contract==="projects.context.select"' in script
    assert 'event.detail?.module?.module_id===moduleId' in script
    assert "projects.core" not in script
    assert "window.FieldoraProjects" not in script


def test_non_app_responses_are_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_dossier_module_response("/api/v1/dossiers", original) is original
