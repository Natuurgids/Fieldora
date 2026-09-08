from __future__ import annotations

import pytest

from natureai_next.server.api import ApiResponse
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


def test_foundation_composition_can_disable_independent_module() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "knowledge.center"
    )

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
    )
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


def test_foundation_composition_rejects_unknown_enabled_module() -> None:
    with pytest.raises(WebModuleContractError, match="unknown enabled module ids"):
        foundation_composition_registry(("home.activity", "missing.module"))


def test_foundation_composition_rejects_stranded_required_contracts() -> None:
    enabled = tuple(
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != "projects.core"
    )

    with pytest.raises(WebModuleContractError, match="missing contract providers"):
        foundation_composition_registry(enabled)
