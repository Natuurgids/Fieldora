from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)
from natureai_next.server.project_list_provider_web import patch_project_list_provider_response
from natureai_next.server.project_runtime_web import ProjectRuntimeWebApiMixin
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)


def _context_ready(body: bytes) -> ApiResponse:
    base = ApiResponse(200, body, "text/javascript; charset=utf-8")
    shell = patch_modular_shell_response("/app.js", base)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    return patch_project_list_provider_response("/app.js", contracts)


def test_context_provider_rewrites_cockpit_private_selection_write() -> None:
    legacy = b'cockpitProjectId=id||"";selectedProject=cockpitProjectId;'
    script = patch_project_context_provider_response(
        "/app.js", _context_ready(legacy)
    ).body.decode("utf-8")

    assert 'selectedProject=cockpitProjectId' not in script
    assert 'resolve?.("projects.context.select")' in script
    assert 'context?.select?.(cockpitProjectId)' in script


def test_context_provider_rewrites_only_known_project_runtime_private_reads() -> None:
    legacy = (
        b'button.dataset.fieldoraAuthorizationHidden="true";const id=selectedProject||"";'
        b'const host=q("portfolio-project-linked-evidence"),id=selectedProject||"";'
        b'const projectId=selectedProject||"",title=q("portfolio-project-task-title").value.trim();'
        b'const projectId=selectedProject||"",mediaId=q("portfolio-project-evidence").value;'
        b'const ownerLocal=selectedProject||"";'
    )
    script = patch_project_context_provider_response(
        "/app.js", _context_ready(legacy)
    ).body.decode("utf-8")

    assert 'const id=selectedProject||"";' not in script
    assert ',id=selectedProject||"";' not in script
    assert 'const projectId=selectedProject||"",title=' not in script
    assert 'const projectId=selectedProject||"",mediaId=' not in script
    assert script.count(
        'window.FieldoraModuleContracts?.resolve?.("projects.context.select")?.current?.()||""'
    ) == 4
    assert 'const ownerLocal=selectedProject||"";' in script


def test_production_rewrites_cockpit_and_runtime_private_project_state_access() -> None:
    base = patch_modular_shell_response(
        "/app.js",
        ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8"),
    )
    cockpit = patch_project_facility_workspace_response("/app.js", base)
    runtime = ProjectRuntimeWebApiMixin._patch_project_runtime_response(
        "/app.js", cockpit
    )
    final = patch_managed_web_response("/app.js", runtime)
    script = final.body.decode("utf-8")

    assert 'selectedProject=cockpitProjectId' not in script
    assert 'const id=selectedProject||"";' not in script
    assert ',id=selectedProject||"";' not in script
    assert 'const projectId=selectedProject||"",title=' not in script
    assert 'const projectId=selectedProject||"",mediaId=' not in script
    assert 'context?.select?.(cockpitProjectId)' in script
    assert 'resolve?.("projects.context.select")?.current?.()' in script
