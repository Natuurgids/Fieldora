from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_composition import (
    finalize_modular_shell_response,
    foundation_composition_registry,
)
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)


def _installed_navigation_shell() -> ApiResponse:
    response = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    response = patch_navigation_web_response("/app.js", response)
    return patch_modular_shell_response("/app.js", response)


def test_operations_owns_related_project_wiring_through_workspace_snapshot() -> None:
    final = finalize_modular_shell_response("/app.js", _installed_navigation_shell())
    script = final.body.decode("utf-8")

    assert "WEB-OPERATIONS-RELATED-PROJECT" in script
    assert 'host.records?.()' in script
    assert 'host.currentDomain?.()' in script
    assert 'resolve("projects.context.select")' in script
    assert 'resolve("navigation.navigate")' in script
    assert 'const items=JSON.parse(operations.dataset.records||"[]")' not in script
    assert "oldOperationsClick" not in script


def test_operations_declares_project_context_as_optional_contract() -> None:
    registry = foundation_composition_registry()
    operations = registry.extension_mapping()[OPERATIONS_WEB_MODULE_ID]

    assert operations.requires_contracts == (
        "operations.workspace.host",
        "navigation.navigate",
    )
    assert operations.optional_contracts == ("projects.context.select",)


def test_operations_adapter_is_absent_when_operations_is_omitted() -> None:
    enabled = (
        "home.activity",
        "library.catalog",
        "observations.core",
        "knowledge.center",
        "admin.shell",
        FACILITIES_WEB_MODULE_ID,
    )
    registry = foundation_composition_registry(enabled)

    final = finalize_modular_shell_response(
        "/app.js", _installed_navigation_shell(), registry=registry
    )
    script = final.body.decode("utf-8")

    assert not registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert "WEB-OPERATIONS-RELATED-PROJECT" not in script


def test_operations_remains_composable_without_projects() -> None:
    enabled = (
        "home.activity",
        "library.catalog",
        "observations.core",
        "knowledge.center",
        "admin.shell",
        OPERATIONS_WEB_MODULE_ID,
        FACILITIES_WEB_MODULE_ID,
    )
    registry = foundation_composition_registry(enabled)

    assert registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert registry.contract_provider("projects.context.select") is None
    operations = registry.extension_mapping()[OPERATIONS_WEB_MODULE_ID]
    assert "projects.context.select" in operations.optional_contracts
