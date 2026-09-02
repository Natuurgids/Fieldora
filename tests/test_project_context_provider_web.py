from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)


def test_context_provider_requires_project_owner_and_contract_runtime() -> None:
    plain = ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    assert patch_project_context_provider_response("/app.js", plain) is plain

    project = patch_project_core_module_response("/app.js", plain)
    assert patch_project_context_provider_response("/app.js", project) is project

    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    patched = patch_project_context_provider_response("/app.js", contracts)
    patched_again = patch_project_context_provider_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-CONTEXT-PROVIDER") == 1
    assert 'contractName="projects.context.select"' in script
    assert "contracts.register(contractName,moduleId,implementation)" in script
    assert "projects.selectProject(id)" in script
    assert "owner()?.currentProject?.()" in script


def test_context_provider_exposes_contract_not_portfolio_navigation() -> None:
    project = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    script = patch_project_context_provider_response("/app.js", contracts).body.decode(
        "utf-8"
    )

    assert "window.FieldoraProjectContext=implementation" in script
    assert "window.openProject" not in script


def test_production_patch_composes_context_provider_after_runtime() -> None:
    project = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    shell = patch_modular_shell_response("/app.js", project)
    final = patch_managed_web_response("/app.js", shell)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULE-CONTRACT-RUNTIME") == 1
    assert script.count("WEB-PROJECT-LIST-PROVIDER") == 1
    assert script.count("WEB-PROJECT-CONTEXT-PROVIDER") == 1
    assert script.rfind("WEB-PROJECT-CONTEXT-PROVIDER") > script.rfind(
        "WEB-MODULE-CONTRACT-RUNTIME"
    )
