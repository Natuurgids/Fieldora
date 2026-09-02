from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.portfolio_module_web import (
    PortfolioModuleWebApiMixin,
    patch_portfolio_module_response,
)


def test_portfolio_module_patch_is_idempotent_and_lifecycle_owned() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")

    patched = patch_portfolio_module_response("/app.js", original)
    patched_again = patch_portfolio_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "window.FieldoraPortfolio" in script
    assert 'const moduleId="portfolio"' in script
    assert "fieldora:module-mount" in script
    assert "fieldora:module-unmount" in script
    assert "new AbortController()" in script
    assert "fieldora:module-error" in script
    assert "loadPortfolio=async function" not in script
    assert "showPage=function" not in script


def test_portfolio_module_uses_projects_contracts_and_owns_work_data_loading() -> None:
    patched = patch_portfolio_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.list.read")' in script
    assert 'resolve?.("projects.context.select")' in script
    assert "allProjects=projectList()?.items?.()||[]" in script
    assert "if(list?.refresh)await list.refresh()" in script
    assert "context.select(rowNode.dataset.portfolioId)" in script
    assert "window.projects" not in script
    assert "window.openProject" not in script
    assert "window.loadPortfolio" not in script
    assert 'fetchItems("phases")' in script
    assert 'fetchItems("tasks")' in script
    assert 'fetchItems("sprints")' in script
    assert "data-portfolio-id" in script
    assert "data-portfolio-view" in script
    assert 'q("portfolio-scope")' in script


def test_portfolio_retries_list_refresh_when_contract_registers_late() -> None:
    patched = patch_portfolio_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "fieldora:contract-registered" in script
    assert 'event.detail?.contract==="projects.list.read"&&state.mounted' in script
    assert "fieldora:project-list-changed" in script


def test_final_composition_removes_shared_portfolio_override_but_keeps_other_legacy_features() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = patch_navigation_web_response("/app.js", base)
    assert b"loadPortfolio=async function" in legacy.body
    assert b"loadKnowledge=async function" in legacy.body

    portfolio = patch_portfolio_module_response("/app.js", legacy)
    final = patch_modular_shell_response("/app.js", portfolio)
    script = final.body.decode("utf-8")

    assert "window.FieldoraPortfolio" in script
    assert "loadPortfolio=async function" not in script
    assert "loadKnowledge=async function" in script
    assert "showPage=function(name)" not in script
    assert "window.FieldoraModules" in script


def test_portfolio_module_is_composed_inside_modular_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1] is not PortfolioModuleWebApiMixin
    assert PortfolioModuleWebApiMixin in mro[2:]
