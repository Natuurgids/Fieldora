from __future__ import annotations

import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_web import patch_facility_actions_response
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_composition import (
    foundation_composition_registry,
    modular_shell_bootstrap,
    modular_shell_surface_filter,
)
from natureai_next.server.modular_shell_web import (
    patch_modular_shell_response as install_modular_shell_response,
)
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleContractError,
)
from natureai_next.server.web_module_extensions import FACILITIES_WEB_MODULE_ID


def test_foundation_composition_can_disable_independent_module() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "knowledge.center"
    ) + (FACILITIES_WEB_MODULE_ID,)

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
    ) + (FACILITIES_WEB_MODULE_ID,)
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


def test_facilities_is_a_non_route_composition_identity() -> None:
    registry = foundation_composition_registry()

    assert registry.is_composed(FACILITIES_WEB_MODULE_ID)
    assert registry.resolve("/operations") is None
    assert '"module_id":"facilities"' not in modular_shell_bootstrap(registry).decode(
        "utf-8"
    )


def test_facilities_omission_suppresses_facility_browser_projections() -> None:
    enabled = tuple(spec.module_id for spec in FOUNDATION_WEB_MODULES)
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
    assert "window.__fieldoraFacilityActions" not in script
    assert "facility-planning-web" not in script
    assert "facility-desktop-cockpit" not in script
    assert '"module_id":"projects.core"' in script


def test_facilities_projection_remains_when_composed() -> None:
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
    assert "facility-planning-web" in script
    assert "facility-desktop-cockpit" in script


def test_foundation_composition_rejects_unknown_enabled_module() -> None:
    with pytest.raises(WebModuleContractError, match="unknown enabled module ids"):
        foundation_composition_registry(("home.activity", "missing.module"))


def test_foundation_composition_rejects_stranded_required_contracts() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "projects.core"
    ) + (FACILITIES_WEB_MODULE_ID,)

    with pytest.raises(WebModuleContractError, match="missing contract providers"):
        foundation_composition_registry(enabled)
