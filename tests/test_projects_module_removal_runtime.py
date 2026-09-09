from __future__ import annotations

from natureai_next.server import modular_shell_composition, web_module_contract_runtime
from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleRegistry,
)

_PROJECT_CONTRACTS = {
    "projects.list.read",
    "projects.context.select",
    "projects.toolbar.extend",
    "projects.selected-record.select",
    "projects.work-data.service",
    "projects.evidence.service",
}
_PROJECT_MODULES = {
    "projects.core",
    "portfolio",
    "capacity",
    "research.dossiers",
    "dossiers.workspace",
}
_PROJECT_ROUTES = {
    "/projects",
    "/portfolio",
    "/capacity",
    "/research",
    "/dossiers",
}
_UNRELATED_MODULES = {
    "home.activity",
    "library.catalog",
    "observations.core",
    "knowledge.center",
    "admin.shell",
}


def _projects_free_registry() -> WebModuleRegistry:
    registry = WebModuleRegistry(
        spec for spec in FOUNDATION_WEB_MODULES if spec.module_id not in _PROJECT_MODULES
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry


def test_projects_free_registry_generates_shell_and_contract_runtime() -> None:
    registry = _projects_free_registry()

    shell = modular_shell_composition.modular_shell_bootstrap(registry).decode("utf-8")
    surface_filter = modular_shell_composition.modular_shell_surface_filter(registry).decode(
        "utf-8"
    )
    contracts = web_module_contract_runtime._runtime_script(registry).decode("utf-8")

    for module_id in _PROJECT_MODULES:
        marker = f'"module_id":"{module_id}"'
        assert marker not in shell
        assert marker not in contracts

    for module_id in _UNRELATED_MODULES:
        marker = f'"module_id":"{module_id}"'
        assert marker in shell
        assert marker in contracts

    for route in _PROJECT_ROUTES:
        assert f'"{route.lstrip("/")}"' in surface_filter

    for route in {"/home", "/library", "/observations", "/knowledge", "/administration"}:
        assert f'"{route.lstrip("/")}"' not in surface_filter

    for contract in _PROJECT_CONTRACTS:
        assert contract not in contracts

    assert "window.FieldoraModules=Object.freeze" in shell
    assert "window.FieldoraModuleContracts=Object.freeze" in contracts
    assert '"route":"/home"' in shell
    assert '"route":"/library"' in shell
    assert '"route":"/observations"' in shell
    assert '"route":"/knowledge"' in shell
    assert '"route":"/administration"' in shell


def test_projects_free_production_composition_omits_projects_owned_providers() -> None:
    registry = _projects_free_registry()
    shell = patch_modular_shell_response(
        "/app.js",
        ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8"),
    )

    script = patch_managed_web_response(
        "/app.js", shell, registry=registry
    ).body.decode("utf-8")

    for marker in (
        "WEB-PROJECT-WORK-DATA-PROVIDER",
        "WEB-PROJECT-EVIDENCE-SERVICE-PROVIDER",
        "WEB-PROJECT-LIST-PROVIDER",
        "WEB-PROJECT-CONTEXT-PROVIDER",
    ):
        assert marker not in script

    assert '"module_id":"home.activity"' in script
    assert '"module_id":"projects.core"' not in script
