from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
    runtime_contract_manifest,
)


def test_runtime_manifest_publishes_project_provider_and_portfolio_requirements() -> None:
    by_id = {item["module_id"]: item for item in runtime_contract_manifest()}

    assert by_id["projects.core"]["provides_contracts"] == [
        "projects.list.read",
        "projects.context.select",
    ]
    assert by_id["portfolio"]["requires_contracts"] == [
        "projects.list.read",
        "projects.context.select",
    ]


def test_runtime_registry_is_inert_without_modular_shell_and_idempotent_with_it() -> None:
    plain = ApiResponse(200, b"const plain=true;", "text/javascript; charset=utf-8")
    assert patch_runtime_contracts_response("/app.js", plain) is plain

    shell = patch_modular_shell_response("/app.js", plain)
    patched = patch_runtime_contracts_response("/app.js", shell)
    patched_again = patch_runtime_contracts_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-MODULE-CONTRACT-RUNTIME") == 1
    assert "window.FieldoraModuleContracts" in script
    assert "function provider(contract)" in script
    assert "function register(contract,moduleId,implementation)" in script
    assert "function requireContract(contract)" in script
    assert "fieldora:contract-registered" in script
    assert "fieldora:contracts-ready" in script
    assert script.index("WEB-MODULAR-SHELL") < script.index("WEB-MODULE-CONTRACT-RUNTIME")


def test_runtime_registry_rejects_wrong_or_duplicate_provider_in_script_contract() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patch_runtime_contracts_response("/app.js", shell).body.decode("utf-8")

    assert "Unknown module contract" in script
    assert "is provided by ${expected}, not ${owner}" in script
    assert "Contract already registered" in script
    assert "Required module contract is not registered" in script


def test_production_managed_patch_places_contract_runtime_after_finalized_shell() -> None:
    shell = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    final = patch_managed_web_response("/app.js", shell)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULAR-SHELL: registry-owned navigation bridge") == 1
    assert script.count("WEB-MODULE-CONTRACT-RUNTIME") == 1
    assert script.rfind("WEB-MODULE-CONTRACT-RUNTIME") > script.rfind(
        "WEB-MODULAR-SHELL: registry-owned navigation bridge"
    )
