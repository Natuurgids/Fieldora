from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import (
    ModularShellWebApiMixin,
    modular_shell_manifest,
    patch_modular_shell_response,
)
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


def test_manifest_exposes_distinct_project_and_portfolio_owners() -> None:
    by_id = {item["module_id"]: item for item in modular_shell_manifest()}

    assert by_id["projects.core"]["route"] == "/projects"
    assert by_id["portfolio"]["route"] == "/portfolio"
    assert by_id["portfolio"]["dependencies"] == ["projects.core"]
    assert by_id["admin.shell"]["capability"] == "administration.view"


def test_app_script_receives_registry_owned_shell_bridge_once() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript; charset=utf-8")

    patched = patch_modular_shell_response("/app.js", original)
    patched_again = patch_modular_shell_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "window.FieldoraModules" in script
    assert "fieldora:module-mount" in script
    assert "fieldora:module-unmount" in script
    assert '"module_id":"projects.core"' in script
    assert '"module_id":"portfolio"' in script
    assert "showPage=function" not in script
    assert "loadPortfolio=async function" not in script


def test_non_app_script_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_modular_shell_response("/api/v1/status", original) is original


def test_modular_shell_is_outermost_managed_web_mixin() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1] is ModularShellWebApiMixin
