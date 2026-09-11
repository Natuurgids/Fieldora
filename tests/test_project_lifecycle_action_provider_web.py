from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_lifecycle_module_web import (
    patch_project_lifecycle_module_response,
)
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_lifecycle_commands_are_existing_projects_core_actions() -> None:
    registry = foundation_registry()

    for action in (
        "projects.create",
        "projects.details.edit",
        "projects.status.change",
        "projects.archive",
    ):
        owner = registry.action_owner(action)
        assert owner is not None
        assert owner.module_id == "projects.core"


def test_lifecycle_action_provider_preserves_governed_routes() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    runtime = patch_runtime_contracts_response("/app.js", shell)
    patched = patch_project_lifecycle_module_response("/app.js", runtime)
    patched_again = patch_project_lifecycle_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-LIFECYCLE-ACTION-PROVIDER") == 1
    assert 'moduleId="projects.core"' in script
    assert 'api("/api/v1/projects",{method:"POST",purpose:"research"' not in script
    assert 'api(`/api/v1/projects/${encodeURIComponent(id)}`,{method:"PATCH",purpose:"research"' in script
    assert 'api(`/api/v1/projects/${encodeURIComponent(id)}/status`,{method:"PATCH",purpose:"research"' in script
    assert 'api(`/api/v1/projects/${encodeURIComponent(id)}/archive`,{method:"PATCH",purpose:"research"' in script
    assert "JSON.stringify({expected_revision:expectedRevision,status})" in script
    assert "JSON.stringify({expected_revision:expectedRevision})" in script
    assert '"projects.create":create' not in script
    assert '"projects.details.edit":update' in script
    assert '"projects.status.change":changeStatus' in script
    assert '"projects.archive":archive' in script
    assert "contracts.registerAction(name,moduleId,implementation)" in script
    assert "fieldora:contracts-ready" in script
    assert "return freezeItem(result?.item)" in script


def test_provider_slice_does_not_yet_move_lifecycle_presentation_transport() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "WEB-PROJECT-LIFECYCLE-MODULE" in script
    assert 'method:"PATCH",purpose:"research"' in script
    assert 'resolveAction("projects.details.edit")' not in script
