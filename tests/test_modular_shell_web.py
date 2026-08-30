from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import (
    ModularShellWebApiMixin,
    modular_shell_manifest,
    patch_modular_shell_response,
)
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
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


def test_modular_shell_owns_navigation_and_browser_history_without_replacing_renderer() -> None:
    patched = patch_modular_shell_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "function navigate(value,source='shell',historyMode='push')" in script
    assert "history.pushState" in script
    assert "history.replaceState" in script
    assert "window.addEventListener('hashchange'" in script
    assert "window.addEventListener('popstate'" in script
    assert "window.showPage(page)" in script
    assert "showPage=function" not in script


def test_final_composed_response_removes_legacy_show_page_history_wrapper() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = patch_navigation_web_response("/app.js", base)
    assert b"showPage=function(name)" in legacy.body

    final = patch_modular_shell_response("/app.js", legacy)
    script = final.body.decode("utf-8")

    assert "const baseApp=true" in script
    assert "oldShowPage=showPage" not in script
    assert "showPage=function(name)" not in script
    assert "window.FieldoraModules" in script
    # Feature compatibility remains until those responsibilities migrate into
    # their owning modules; this change removes routing/history coupling only.
    assert "loadPortfolio=async function" in script


def test_non_app_script_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_modular_shell_response("/api/v1/status", original) is original


def test_modular_shell_is_outermost_managed_web_mixin() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1] is ModularShellWebApiMixin
