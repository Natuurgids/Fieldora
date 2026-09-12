from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_module_web import patch_dossier_module_response
from natureai_next.server.web_module_contracts import foundation_registry


# Service boundary certification.
def test_dossier_module_is_idempotent_and_owns_workspace_behavior() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_dossier_module_response("/app.js", original)
    again = patch_dossier_module_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-DOSSIER-DATA-SERVICE" in script
    assert "WEB-DOSSIER-MODULE" in script
    provider = script.split("WEB-DOSSIER-DATA-SERVICE", 1)[1].split("WEB-DOSSIER-MODULE", 1)[0]
    presentation = script.split("WEB-DOSSIER-MODULE", 1)[1]
    assert 'const moduleId="dossiers.workspace"' in presentation
    assert "window.FieldoraDossiers=Object.freeze" in presentation
    assert 'q("page-dossiers")' in presentation
    assert 'q("dossier-refresh")?.addEventListener("click",refresh' in presentation
    assert 'q("dossier-save")?.addEventListener("click",save' in presentation
    assert 'q("dossier-workspace-list")?.addEventListener("click"' in presentation
    assert 'api("/api/v1/dossiers")' in provider
    assert 'api("/api/v1/dossier-reviews")' in provider
    assert 'async function updateDossier(dossierId,record)' in provider
    assert '/owner/reassign' in provider
    assert '/review/defer' in provider
    assert '/review/remark' in provider
    assert '/review/return' in provider
    assert 'resolve?.("dossiers.data.service")' in presentation
    assert "api(" not in presentation
    assert 'fieldora:dossier-workspace-changed' in presentation


def test_dossier_module_exposes_governed_lifecycle_controls() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")
    provider = script.split("WEB-DOSSIER-DATA-SERVICE", 1)[1].split("WEB-DOSSIER-MODULE", 1)[0]
    presentation = script.split("WEB-DOSSIER-MODULE", 1)[1]

    assert 'id="dossier-lifecycle-panel"' in presentation
    assert 'id="dossier-lifecycle-update"' in presentation
    assert 'id="dossier-lifecycle-type"' in presentation
    assert 'q("dossier-lifecycle-type").value=dossier.dossier_type==="master"?"master":"dossier"' in presentation
    assert 'dossier_type:q("dossier-lifecycle-type")?.value||"dossier"' in presentation
    assert 'id="dossier-lifecycle-project"' in presentation
    assert 'id="dossier-lifecycle-use-project"' in presentation
    assert 'id="dossier-lifecycle-independent"' in presentation
    assert 'service.updateDossier(dossier.id,{project_id:String(projectId||"")})' in presentation
    assert 'const projectId=syncProjectContext();if(!projectId)' in presentation
    assert 'id="dossier-lifecycle-owner"' in presentation
    assert 'id="dossier-lifecycle-reassign-owner"' in presentation
    assert 'id="dossier-lifecycle-defer"' in presentation
    assert 'id="dossier-lifecycle-remark-action"' in presentation
    assert 'id="dossier-lifecycle-return"' in presentation
    assert 'service.updateDossier(dossier.id' in presentation
    assert 'service.reassignOwner(dossier.id' in presentation
    assert 'service.deferReview(dossier.id' in presentation
    assert 'service.remarkReview(dossier.id' in presentation
    assert 'service.returnReview(dossier.id' in presentation
    assert 'method:"PATCH"' in provider
    assert 'method:"POST"' in provider
    assert "api(" not in presentation


def test_dossier_registry_declares_data_service_provider() -> None:
    registry = foundation_registry()
    dossiers = registry.resolve("/dossiers")

    assert dossiers is not None
    assert dossiers.provides_contracts == ("dossiers.data.service",)
    assert registry.contract_provider("dossiers.data.service") is dossiers


def test_dossier_module_uses_notification_contract_for_errors() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")

    assert 'resolve?.("notifications.publish")' in script
    assert 'notifications()?.publish?.(String(text),{level:"error",source_module:moduleId})' in script
    assert 'fieldora:module-error' not in script


def test_dossier_module_uses_auth_contract_for_identity() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")

    assert 'resolve?.("auth.current-user")?.current?.()' in script
    assert 'const identity=currentUser()' in script
    assert 'state.identityId=String(identity?.identity_id||"")' in script
    assert 'api("/api/v1/me")' not in script
    assert "window.me" not in script


def test_dossier_module_uses_only_canonical_project_context_and_fails_closed() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    script = patch_dossier_module_response("/app.js", original).body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert 'function currentProject(){return String(context()?.current?.()||"")}' in script
    assert 'Select a Project before creating a dossier.' in script
    assert 'Select a Project before moving the dossier.' in script
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
