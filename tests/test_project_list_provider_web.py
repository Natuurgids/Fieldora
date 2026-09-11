from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_list_provider_web import (
    patch_project_list_provider_response,
)
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)


def test_project_list_provider_requires_contract_runtime_and_is_idempotent() -> None:
    plain = ApiResponse(200, b"const plain=true;", "text/javascript; charset=utf-8")
    assert patch_project_list_provider_response("/app.js", plain) is plain

    shell = patch_modular_shell_response("/app.js", plain)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    patched = patch_project_list_provider_response("/app.js", contracts)
    patched_again = patch_project_list_provider_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-LIST-PROVIDER") == 1
    assert 'contractName="projects.list.read"' in script
    assert "contracts.register(contractName,moduleId,implementation)" in script
    assert "Object.freeze(state.items.map" in script
    assert "fieldora:project-list-changed" in script
    assert "window.FieldoraProjectList=implementation" in script


def test_project_list_provider_owns_and_deduplicates_refresh() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    contracts = patch_runtime_contracts_response("/app.js", shell)
    script = patch_project_list_provider_response("/app.js", contracts).body.decode(
        "utf-8"
    )

    assert "state={items:[],loaded:false,pending:null}" in script
    assert "if(state.pending)return state.pending" in script
    assert "await api('/api/v1/projects',{purpose:'research'})" in script
    assert "state.loaded=true" in script
    assert (
        "const implementation=Object.freeze({items:snapshot,refresh,ready:()=>state.loaded,capabilities})"
        in script
    )
    assert "state.pending===pending" in script
    assert "replace:" not in script


def test_project_list_provider_owns_project_capability_projection() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    contracts = patch_runtime_contracts_response("/app.js", shell)
    script = patch_project_list_provider_response("/app.js", contracts).body.decode(
        "utf-8"
    )

    assert "async function capabilities(projectId)" in script
    assert 'api(`/api/v1/projects/${encodeURIComponent(id)}/capabilities`,{purpose:"research"})' in script
    assert "return Object.freeze({...result,actions})" in script


def test_project_list_provider_bridges_legacy_create_refresh_to_canonical_list() -> None:
    legacy = ApiResponse(
        200,
        b'<button id="portfolio-project-save"></button>',
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    script = patch_project_list_provider_response("/app.js", contracts).body.decode(
        "utf-8"
    )

    assert 'document.getElementById("portfolio-project-save")' in script
    assert 'button.dataset.fieldoraProjectListBridge="true"' in script
    assert "const result=await legacy.apply(this,args);" in script
    assert "await refresh();" in script
    assert "setTimeout(bridgeLegacyCreateRefresh,0);" in script


def test_production_patch_orders_project_list_provider_after_contract_runtime() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    final = patch_managed_web_response("/app.js", shell)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULE-CONTRACT-RUNTIME") == 1
    assert script.count("WEB-PROJECT-LIST-PROVIDER") == 1
    assert script.rfind("WEB-PROJECT-LIST-PROVIDER") > script.rfind(
        "WEB-MODULE-CONTRACT-RUNTIME"
    )
