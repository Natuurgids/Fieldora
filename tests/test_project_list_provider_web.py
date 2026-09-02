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
    assert "window.FieldoraProjectList" in script


def test_project_list_provider_owns_refresh_without_exposing_mutable_replace() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    contracts = patch_runtime_contracts_response("/app.js", shell)
    script = patch_project_list_provider_response("/app.js", contracts).body.decode(
        "utf-8"
    )

    assert "await api('/api/v1/projects',{purpose:'research'})" in script
    assert "const implementation=Object.freeze({items:snapshot,refresh})" in script
    assert "replace:" not in script


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
