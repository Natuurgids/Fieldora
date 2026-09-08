from __future__ import annotations

import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_api import FacilityActionsApiMixin
from natureai_next.server.facility_actions_web import patch_facility_actions_response
from natureai_next.server.facility_module_runtime import (
    FacilityModuleCompositionApiMixin,
)
from natureai_next.server.http import handler_for, patch_managed_web_response
from natureai_next.server.modular_shell_composition import (
    foundation_composition_registry,
    modular_shell_bootstrap,
    modular_shell_surface_filter,
)
from natureai_next.server.modular_shell_web import (
    patch_modular_shell_response as install_modular_shell_response,
)
from natureai_next.server.operations_module_runtime import (
    OperationsModuleCompositionApiMixin,
)
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleContractError,
)
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)


class _RuntimeProbeBase:
    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        content_type = (
            "text/javascript; charset=utf-8"
            if target.partition("?")[0] == "/app.js"
            else "application/json"
        )
        body_value = (
            b"const baseApp=true;"
            if content_type.startswith("text/javascript")
            else b"{}"
        )
        return ApiResponse(200, body_value, content_type)


class _ComposedRuntimeProbe(
    OperationsModuleCompositionApiMixin,
    FacilityModuleCompositionApiMixin,
    FacilityActionsApiMixin,
    _RuntimeProbeBase,
):
    def __init__(self) -> None:
        self._facility_platform = object()


def _route_ids() -> tuple[str, ...]:
    return tuple(spec.module_id for spec in FOUNDATION_WEB_MODULES)


def test_foundation_composition_can_disable_independent_module() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "knowledge.center"
    ) + (OPERATIONS_WEB_MODULE_ID, FACILITIES_WEB_MODULE_ID)

    registry = foundation_composition_registry(enabled)

    assert registry.resolve("/knowledge") is None
    assert registry.resolve("/projects") is not None
    surface_filter = modular_shell_surface_filter(registry).decode("utf-8")
    bootstrap = modular_shell_bootstrap(registry).decode("utf-8")
    assert 'const omitted=["knowledge"]' in surface_filter
    assert '"module_id":"knowledge.center"' not in bootstrap
    assert '"module_id":"projects.core"' in bootstrap


def test_production_finalizer_recomposes_installed_shell_from_registry() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "knowledge.center"
    ) + (OPERATIONS_WEB_MODULE_ID, FACILITIES_WEB_MODULE_ID)
    registry = foundation_composition_registry(enabled)
    original = ApiResponse(
        200,
        b"const baseApp=true;",
        "text/javascript; charset=utf-8",
    )

    installed = install_modular_shell_response("/app.js", original)
    final = patch_managed_web_response("/app.js", installed, registry=registry)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULAR-SHELL: registry-owned navigation bridge") == 1
    assert 'const omitted=["knowledge"]' in script
    assert '"module_id":"knowledge.center"' not in script
    assert '"module_id":"projects.core"' in script


def test_nested_modules_are_non_route_composition_identities() -> None:
    registry = foundation_composition_registry()

    assert registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert registry.resolve("/operations") is None
    bootstrap = modular_shell_bootstrap(registry).decode("utf-8")
    assert '"module_id":"operations"' not in bootstrap
    assert '"module_id":"facilities"' not in bootstrap


def test_facilities_omission_suppresses_facility_browser_projections() -> None:
    enabled = _route_ids() + (OPERATIONS_WEB_MODULE_ID,)
    registry = foundation_composition_registry(enabled)
    original = ApiResponse(
        200,
        b"const baseApp=true;",
        "text/javascript; charset=utf-8",
    )
    installed = install_modular_shell_response("/app.js", original)
    installed = patch_facility_actions_response("/app.js", installed)

    final = patch_managed_web_response("/app.js", installed, registry=registry)
    script = final.body.decode("utf-8")

    assert not registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert "window.__fieldoraFacilityActions" not in script
    assert "window.__fieldoraOfflineMapsWired" not in script
    assert "facility-planning-web" not in script
    assert "facility-desktop-cockpit" not in script
    assert "WEB-FACILITIES-BASE-OMISSION" in script
    assert '["locations","drawings"].forEach' in script
    assert "Asset & Equipment Operations" in script
    assert "WEB-OPERATIONS-BASE-OMISSION" not in script
    assert '"module_id":"projects.core"' in script


def test_facilities_runtime_is_removed_when_omitted() -> None:
    enabled = _route_ids() + (OPERATIONS_WEB_MODULE_ID,)
    registry = foundation_composition_registry(enabled)
    application = _ComposedRuntimeProbe()

    handler_for(application, web_module_registry=registry)

    assert application._operations_composed
    assert not application._facilities_composed
    assert application._facility_platform is None
    facility_paths = (
        "/api/v1/facility-planning/drawings",
        "/api/v1/operations/locations",
        "/api/v1/operations/drawings",
        "/api/v1/operations/storage-conditions",
        "/api/v1/operations/drawing-markers",
        "/api/v1/operations/movements",
    )
    for path in facility_paths:
        assert application.dispatch("GET", path, {}, b"").status == 404

    operations_paths = (
        "/api/v1/operations/assets",
        "/api/v1/operations/maintenance",
        "/api/v1/operations/calibrations",
        "/api/v1/operations/documents",
    )
    for path in operations_paths:
        assert application.dispatch("GET", path, {}, b"").status == 200

    unrelated_response = application.dispatch("GET", "/api/v1/projects", {}, b"")
    assert unrelated_response.status == 200
    browser_response = application.dispatch("GET", "/app.js", {}, b"")
    assert b"window.__fieldoraFacilityActions" not in browser_response.body


def test_operations_omission_preserves_facilities_host() -> None:
    enabled = _route_ids() + (FACILITIES_WEB_MODULE_ID,)
    registry = foundation_composition_registry(enabled)
    original = ApiResponse(
        200,
        b"const baseApp=true;",
        "text/javascript; charset=utf-8",
    )
    installed = install_modular_shell_response("/app.js", original)

    final = patch_managed_web_response("/app.js", installed, registry=registry)
    script = final.body.decode("utf-8")

    assert not registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert "WEB-OPERATIONS-BASE-OMISSION:FACILITIES" in script
    assert '["assets","maintenance","calibrations"].forEach' in script
    assert 'button.textContent="Facilities"' in script
    assert 'operationsDomain="locations"' in script
    assert "WEB-FACILITIES-BASE-OMISSION" not in script


def test_operations_runtime_is_removed_when_omitted() -> None:
    enabled = _route_ids() + (FACILITIES_WEB_MODULE_ID,)
    registry = foundation_composition_registry(enabled)
    application = _ComposedRuntimeProbe()

    handler_for(application, web_module_registry=registry)

    assert not application._operations_composed
    assert application._facilities_composed
    assert application._facility_platform is not None
    operations_paths = (
        "/api/v1/operations/assets",
        "/api/v1/operations/maintenance",
        "/api/v1/operations/calibrations",
        "/api/v1/operations/documents",
    )
    for path in operations_paths:
        assert application.dispatch("GET", path, {}, b"").status == 404

    facility_paths = (
        "/api/v1/operations/locations",
        "/api/v1/operations/drawings",
        "/api/v1/operations/storage-conditions",
        "/api/v1/operations/drawing-markers",
        "/api/v1/operations/movements",
    )
    for path in facility_paths:
        assert application.dispatch("GET", path, {}, b"").status == 200

    unrelated_response = application.dispatch("GET", "/api/v1/projects", {}, b"")
    assert unrelated_response.status == 200


def test_omitting_operations_and_facilities_removes_shared_host() -> None:
    registry = foundation_composition_registry(_route_ids())
    original = ApiResponse(
        200,
        b"const baseApp=true;",
        "text/javascript; charset=utf-8",
    )
    installed = install_modular_shell_response("/app.js", original)

    final = patch_managed_web_response("/app.js", installed, registry=registry)
    script = final.body.decode("utf-8")

    assert not registry.is_composed(OPERATIONS_WEB_MODULE_ID)
    assert not registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert "WEB-FACILITIES-BASE-OMISSION" in script
    assert "WEB-OPERATIONS-BASE-OMISSION:EMPTY" in script
    assert 'data-page="operations"' in script
    assert "Integrations" in script


def test_nested_projections_remain_when_both_modules_are_composed() -> None:
    registry = foundation_composition_registry()
    original = ApiResponse(
        200,
        b"const baseApp=true;",
        "text/javascript; charset=utf-8",
    )
    installed = install_modular_shell_response("/app.js", original)
    installed = patch_facility_actions_response("/app.js", installed)

    final = patch_managed_web_response("/app.js", installed, registry=registry)
    script = final.body.decode("utf-8")

    assert "window.__fieldoraFacilityActions" in script
    assert "window.__fieldoraOfflineMapsWired" in script
    assert "facility-planning-web" in script
    assert "facility-desktop-cockpit" in script
    assert "WEB-FACILITIES-BASE-OMISSION" not in script
    assert "WEB-OPERATIONS-BASE-OMISSION" not in script

    application = _ComposedRuntimeProbe()
    handler_for(application, web_module_registry=registry)
    assert application._operations_composed
    assert application._facilities_composed
    location_response = application.dispatch(
        "GET", "/api/v1/operations/locations", {}, b""
    )
    assert location_response.status == 200
    asset_response = application.dispatch(
        "GET", "/api/v1/operations/assets", {}, b""
    )
    assert asset_response.status == 200


def test_foundation_composition_rejects_unknown_enabled_module() -> None:
    with pytest.raises(WebModuleContractError, match="unknown enabled module ids"):
        foundation_composition_registry(("home.activity", "missing.module"))


def test_foundation_composition_rejects_stranded_required_contracts() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "projects.core"
    ) + (OPERATIONS_WEB_MODULE_ID, FACILITIES_WEB_MODULE_ID)

    with pytest.raises(WebModuleContractError, match="missing contract providers"):
        foundation_composition_registry(enabled)
