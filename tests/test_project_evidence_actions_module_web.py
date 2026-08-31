from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_evidence_actions_module_web import (
    ProjectEvidenceActionsModuleWebApiMixin,
    patch_project_evidence_actions_module_response,
)
from natureai_next.server.project_runtime_web import ProjectRuntimeWebApiMixin
from natureai_next.server.project_work_actions_module_web import (
    patch_project_work_actions_module_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_projects_core_owns_evidence_link_action() -> None:
    owner = foundation_registry().action_owner("projects.evidence.link")

    assert owner is not None
    assert owner.module_id == "projects.core"


def test_evidence_adapter_is_idempotent_and_uses_governed_link_api() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")

    patched = patch_project_evidence_actions_module_response("/app.js", original)
    patched_again = patch_project_evidence_actions_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-EVIDENCE-ACTIONS-MODULE" in script
    assert "window.FieldoraProjectEvidenceActions" in script
    assert "/api/v1/media?limit=200" in script
    assert "/media-links" in script
    assert 'method:"POST",purpose:"research"' in script
    assert "fieldora:project-evidence-changed" in script
    assert "loadPortfolio" not in script
    assert "showPage=" not in script


def test_evidence_link_discoverability_is_not_server_authorization() -> None:
    patched = patch_project_evidence_actions_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "/capabilities" in script
    assert "fieldoraAuthorizationHidden" in script
    assert "caps?.actions?.edit===true" in script
    assert "Choose existing Library evidence." in script
    assert "without changing its identity" in script


def test_final_shell_retires_legacy_project_runtime_only_after_both_replacements() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = ProjectRuntimeWebApiMixin._patch_project_runtime_response("/app.js", base)
    assert "WEB-058: selected Project child work" in legacy.body.decode("utf-8")

    evidence_only = patch_project_evidence_actions_module_response("/app.js", legacy)
    still_legacy = patch_modular_shell_response("/app.js", evidence_only)
    assert "WEB-058: selected Project child work" in still_legacy.body.decode("utf-8")

    both = patch_project_work_actions_module_response("/app.js", evidence_only)
    final = patch_modular_shell_response("/app.js", both)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-EVIDENCE-ACTIONS-MODULE" in script
    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert "WEB-058: selected Project child work" not in script
    assert "portfolio-project-runtime" not in script


def test_evidence_actions_mixin_is_inside_shell_and_outside_project_core() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert ProjectEvidenceActionsModuleWebApiMixin in mro
    assert mro.index(ProjectEvidenceActionsModuleWebApiMixin) < mro.index(
        next(base for base in mro if base.__name__ == "ProjectCoreModuleWebApiMixin")
    )


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_project_evidence_actions_module_response("/api/v1/status", original) is original
