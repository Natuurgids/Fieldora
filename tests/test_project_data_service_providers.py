from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_evidence_service_provider_web import (
    patch_project_evidence_service_provider_response,
)
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)
from natureai_next.server.project_work_data_provider_web import (
    patch_project_work_data_provider_response,
)
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def _contract_runtime() -> ApiResponse:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    return patch_runtime_contracts_response("/app.js", shell)


def test_projects_core_declares_work_and_evidence_service_contracts() -> None:
    projects = foundation_registry().module("projects.core")

    assert "projects.work-data.service" in projects.provides_contracts
    assert "projects.evidence.service" in projects.provides_contracts


def test_work_data_provider_requires_runtime_and_owns_governed_transport() -> None:
    plain = ApiResponse(200, b"const plain=true;", "text/javascript; charset=utf-8")
    assert patch_project_work_data_provider_response("/app.js", plain) is plain

    runtime = _contract_runtime()
    patched = patch_project_work_data_provider_response("/app.js", runtime)
    patched_again = patch_project_work_data_provider_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-WORK-DATA-PROVIDER") == 1
    assert 'contractName="projects.work-data.service"' in script
    assert 'api(`/api/v1/phases?project_id=${pid}`' in script
    assert 'api(`/api/v1/tasks?project_id=${pid}`' in script
    assert 'api(`/api/v1/tasks?project_id=${encodeURIComponent(id)}`' in script
    assert 'api(`/api/v1/phases?project_id=${encodeURIComponent(id)}`' in script
    assert 'api(`/api/v1/sprints?project_id=${encodeURIComponent(id)}`' in script
    assert 'api(`/api/v1/sprints?project_id=${pid}`' in script
    assert 'api(`/api/v1/allocations?project_id=${pid}`' in script
    assert 'api(`/api/v1/project-statuses?project_id=${encodeURIComponent(id)}`' in script
    assert 'api(`/api/v1/tasks/${encodeURIComponent(taskId)}?project_id=${encodeURIComponent(id)}`' in script
    assert 'api(`/api/v1/tasks/${encodeURIComponent(taskId)}`' in script
    assert 'method:"PATCH",purpose:"research"' in script
    assert "JSON.stringify({project_id:id,...(changes||{})})" in script
    assert 'name==="phase"?"/api/v1/phases"' in script
    assert 'name==="sprint"?"/api/v1/sprints"' in script
    assert 'name==="allocation"?"/api/v1/allocations"' in script
    assert "Object.freeze({load,tasks,phases,sprints,statuses,taskDetail,updateTask,create})" in script
    assert "return freezeItems(result?.items)" in script
    assert "return result?.item?Object.freeze({...result.item}):null" in script
    assert "freezeItems" in script


def test_evidence_provider_requires_runtime_and_owns_governed_transport() -> None:
    plain = ApiResponse(200, b"const plain=true;", "text/javascript; charset=utf-8")
    assert patch_project_evidence_service_provider_response("/app.js", plain) is plain

    runtime = _contract_runtime()
    patched = patch_project_evidence_service_provider_response("/app.js", runtime)
    patched_again = patch_project_evidence_service_provider_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-EVIDENCE-SERVICE-PROVIDER") == 1
    assert 'contractName="projects.evidence.service"' in script
    assert "/api/v1/media?project_id=${encodeURIComponent(id)}&limit=200" in script
    assert 'api("/api/v1/media?limit=200"' in script
    assert "/media-links" in script
    assert 'method:"POST",purpose:"research"' in script
    assert "Object.freeze({projectItems,libraryItems,link})" in script
    assert "freezeItems" in script


def test_evidence_provider_does_not_restore_retired_project_cockpit_consumer() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    cockpit = patch_project_facility_workspace_response("/app.js", shell)
    runtime = patch_runtime_contracts_response("/app.js", cockpit)

    patched = patch_project_evidence_service_provider_response("/app.js", runtime)
    script = patched.body.decode("utf-8")

    assert "WEB-PROJECT-EVIDENCE-SERVICE-PROVIDER" in script
    assert "service.projectItems(cockpitProjectId)" not in script
    assert 'api("/api/v1/media?limit=500")' not in script


def test_production_orders_data_services_before_list_provider() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    final = patch_managed_web_response("/app.js", shell)
    script = final.body.decode("utf-8")

    runtime = script.rfind("WEB-MODULE-CONTRACT-RUNTIME")
    work = script.rfind("WEB-PROJECT-WORK-DATA-PROVIDER")
    evidence = script.rfind("WEB-PROJECT-EVIDENCE-SERVICE-PROVIDER")
    projects = script.rfind("WEB-PROJECT-LIST-PROVIDER")

    assert -1 < runtime < work < projects
    assert -1 < runtime < evidence < projects
    assert "service.projectItems(cockpitProjectId)" not in script
    assert 'api("/api/v1/media?limit=500")' not in script
