from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import (
    ModularShellWebApiMixin,
    modular_shell_manifest,
    patch_modular_shell_response,
)
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response
from natureai_next.server.project_core_module_web import (
    ProjectCoreModuleWebApiMixin,
    patch_project_core_module_response,
)
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)


def test_manifest_exposes_distinct_project_and_portfolio_owners() -> None:
    by_id = {item["module_id"]: item for item in modular_shell_manifest()}

    assert by_id["projects.core"]["route"] == "/projects"
    project_actions = set(by_id["projects.core"]["owns_actions"])
    assert {
        "projects.create",
        "projects.context.select",
        "projects.scope.select",
        "projects.center.select",
        "projects.progress.refresh",
        "projects.planning.view.select",
        "projects.task.status.move",
        "projects.gantt.inspect",
        "projects.evidence.load",
        "projects.work.inspect",
        "projects.task.edit",
        "projects.status.change",
    } <= project_actions
    assert by_id["portfolio"]["route"] == "/portfolio"
    assert by_id["portfolio"]["dependencies"] == []
    assert by_id["portfolio"]["owns_actions"] == [
        "portfolio.view.select",
        "portfolio.scope.select",
        "portfolio.project.open",
    ]
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


def test_project_core_owner_removes_legacy_projects_page_portfolio_load() -> None:
    base = ApiResponse(
        200,
        b'function showPage(name){if(name==="projects")loadPortfolio();}',
        "text/javascript; charset=utf-8",
    )
    owned = patch_project_core_module_response("/app.js", base)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert 'if(name==="projects")loadPortfolio();' not in script
    assert "WEB-PROJECT-CORE-MODULE" in script


def test_portfolio_owner_removes_legacy_scope_refresh_wiring() -> None:
    base = ApiResponse(
        200,
        b'q("portfolio-scope").onchange=loadPortfolio;',
        "text/javascript; charset=utf-8",
    )
    owned = patch_portfolio_module_response("/app.js", base)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert 'q("portfolio-scope").onchange=loadPortfolio;' not in script
    assert "WEB-PORTFOLIO-MODULE" in script


def test_portfolio_owner_removes_legacy_view_refresh_wiring() -> None:
    legacy = b'document.querySelectorAll("[data-portfolio-view]").forEach(b=>b.onclick=()=>{portfolioView=b.dataset.portfolioView;document.querySelectorAll("[data-portfolio-view]").forEach(x=>x.classList.toggle("primary",x===b));loadPortfolio()});'
    base = ApiResponse(200, legacy, "text/javascript; charset=utf-8")
    owned = patch_portfolio_module_response("/app.js", base)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert legacy.decode("utf-8") not in script
    assert "WEB-PORTFOLIO-MODULE" in script


def test_project_core_owner_routes_legacy_work_save_refresh_through_event() -> None:
    legacy = b'if(await saveGeneric(path,item,"work-status",`${type} saved.`))loadPortfolio()'
    base = ApiResponse(200, legacy, "text/javascript; charset=utf-8")
    owned = patch_project_core_module_response("/app.js", base)
    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert legacy.decode("utf-8") not in script
    assert "fieldora:project-work-changed" in script
    assert 'module_id:"legacy.work-editor"' in script
    assert "project_id:project" in script
    assert "WEB-PROJECT-CORE-MODULE" in script


def test_final_composed_response_removes_migrated_navigation_and_portfolio_wiring() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    owned = patch_portfolio_module_response("/app.js", base)
    legacy = patch_navigation_web_response("/app.js", owned)
    assert b"showPage=function(name)" in legacy.body
    assert b"loadPortfolio=async function" in legacy.body
    assert b"loadKnowledge=async function" in legacy.body

    final = patch_modular_shell_response("/app.js", legacy)
    script = final.body.decode("utf-8")

    assert "const baseApp=true" in script
    assert "oldShowPage=showPage" not in script
    assert "showPage=function(name)" not in script
    assert "loadPortfolio=async function" not in script
    assert 'q("portfolio-refresh").onclick=loadPortfolio' not in script
    assert "window.FieldoraModules" in script
    assert "WEB-PORTFOLIO-MODULE" in script
    assert "loadKnowledge=async function" in script


def test_final_composed_response_removes_project_cockpit_owned_behavior() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    owned = patch_project_core_module_response("/app.js", base)
    owned = patch_portfolio_module_response("/app.js", owned)
    cockpit = patch_project_facility_workspace_response("/app.js", owned)
    before = cockpit.body.decode("utf-8")

    assert "function renderProjectTree()" in before
    assert "function portfolioData()" in before
    assert "const oldPortfolio=loadPortfolio" in before
    assert "project-desktop-cockpit" in before
    assert "facility-desktop-cockpit" in before

    final = patch_modular_shell_response("/app.js", cockpit)
    script = final.body.decode("utf-8")

    assert "function renderProjectTree()" not in script
    assert "function selectCockpitProject" not in script
    assert "function portfolioData()" not in script
    assert "applyPortfolioView()" not in script
    assert "const oldPortfolio=loadPortfolio" not in script
    assert 'q("portfolio-scope").value=b.dataset.projectScope' not in script
    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "WEB-PORTFOLIO-MODULE" in script
    assert "project-desktop-cockpit" in script
    assert "facility-desktop-cockpit" in script


def test_production_patch_order_finalizes_after_legacy_append_only_patches() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    owned = patch_project_core_module_response("/app.js", base)
    owned = patch_portfolio_module_response("/app.js", owned)
    early = patch_modular_shell_response("/app.js", owned)
    final = patch_managed_web_response("/app.js", early)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULAR-SHELL: registry-owned navigation bridge") == 1
    assert "oldShowPage=showPage" not in script
    assert "showPage=function(name)" not in script
    assert "loadPortfolio=async function" not in script
    assert "function renderProjectTree()" not in script
    assert "function portfolioData()" not in script
    assert "const oldPortfolio=loadPortfolio" not in script
    assert "loadKnowledge=async function" in script
    assert "project-desktop-cockpit" in script
    assert "facility-desktop-cockpit" in script
    assert script.rfind("WEB-MODULAR-SHELL: registry-owned navigation bridge") > script.find(
        "facility-desktop-cockpit"
    )


def test_managed_web_finalizer_is_inert_without_modular_shell() -> None:
    original = ApiResponse(200, b"const plainFieldora=true;", "text/javascript; charset=utf-8")
    final = patch_managed_web_response("/app.js", original)
    script = final.body.decode("utf-8")

    assert "WEB-MODULAR-SHELL: registry-owned navigation bridge" not in script
    assert "showPage=function(name)" in script
    assert "function renderProjectTree()" in script


def test_non_app_script_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_modular_shell_response("/api/v1/status", original) is original


def test_modular_shell_is_outermost_and_project_core_is_composed() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1] is ModularShellWebApiMixin
    assert ProjectCoreModuleWebApiMixin in mro[2:]
