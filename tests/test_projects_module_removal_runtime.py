from __future__ import annotations

from natureai_next.server import modular_shell_web, web_module_contract_runtime
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleRegistry,
)

_PROJECT_CONTRACTS = {
    "projects.list.read",
    "projects.context.select",
    "projects.toolbar.extend",
}
_PROJECT_MODULES = {
    "projects.core",
    "portfolio",
    "capacity",
    "research.dossiers",
    "dossiers.workspace",
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


def test_projects_free_registry_generates_shell_and_contract_runtime(monkeypatch) -> None:
    registry = _projects_free_registry()
    monkeypatch.setattr(modular_shell_web, "foundation_registry", lambda: registry)
    monkeypatch.setattr(web_module_contract_runtime, "foundation_registry", lambda: registry)

    shell = modular_shell_web._bootstrap_script().decode("utf-8")
    contracts = web_module_contract_runtime._runtime_script().decode("utf-8")

    for module_id in _PROJECT_MODULES:
        marker = f'"module_id":"{module_id}"'
        assert marker not in shell
        assert marker not in contracts

    for module_id in _UNRELATED_MODULES:
        marker = f'"module_id":"{module_id}"'
        assert marker in shell
        assert marker in contracts

    for contract in _PROJECT_CONTRACTS:
        assert contract not in contracts

    assert "window.FieldoraModules=Object.freeze" in shell
    assert "window.FieldoraModuleContracts=Object.freeze" in contracts
    assert '"route":"/home"' in shell
    assert '"route":"/library"' in shell
    assert '"route":"/observations"' in shell
    assert '"route":"/knowledge"' in shell
    assert '"route":"/administration"' in shell
