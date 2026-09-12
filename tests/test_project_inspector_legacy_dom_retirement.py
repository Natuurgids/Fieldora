from __future__ import annotations

from playwright.sync_api import sync_playwright

from natureai_next.server.project_core_module_web import _PROJECT_CORE_MODULE_PATCH
from natureai_next.server.project_inspector_module_web import _PROJECT_INSPECTOR_MODULE_PATCH
from natureai_next.server.project_selected_record_provider_web import (
    _SELECTED_RECORD_PROVIDER_PATCH,
)
from natureai_next.server.web_module_contract_runtime import _runtime_script


def _install_script(page, script: bytes) -> None:
    page.add_script_tag(content=script.decode("utf-8"))


def test_project_inspector_does_not_reparent_legacy_portfolio_or_work_editor_dom() -> None:
    script = _PROJECT_INSPECTOR_MODULE_PATCH.decode("utf-8")
    assert 'q("portfolio-detail")' not in script
    assert 'q("work-editor")' not in script
    assert "Create / update work item" not in script

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """
            <section id="page-projects"><div class="top"><h1>Projects</h1></div></section>
            <section id="legacy-portfolio-owner"><div class="card"><div id="portfolio-detail">Legacy portfolio detail</div></div></section>
            <section id="legacy-work-owner"><div id="work-editor">Legacy work editor</div></section>
            """
        )
        _install_script(page, _runtime_script())
        _install_script(page, _SELECTED_RECORD_PROVIDER_PATCH)
        _install_script(page, _PROJECT_CORE_MODULE_PATCH)
        _install_script(page, _PROJECT_INSPECTOR_MODULE_PATCH)

        assert page.locator("#portfolio-detail").evaluate("node => node.parentElement.parentElement.id") == "legacy-portfolio-owner"
        assert page.locator("#work-editor").evaluate("node => node.parentElement.id") == "legacy-work-owner"

        page.evaluate(
            """
            FieldoraModuleContracts.resolve('projects.selected-record.select').select({
              kind:'task',id:'task-1',record:{
                id:'task-1',title:'Owned task',status:'active',owner_id:'scientist-1',description:'Inspector-owned properties'
              }
            })
            """
        )

        properties = page.locator("#project-inspector-properties-content")
        assert "Owned task" in properties.inner_text()
        assert "task" in properties.inner_text()
        assert "scientist-1" in properties.inner_text()
        assert "Inspector-owned properties" in properties.inner_text()
        assert page.locator("#portfolio-detail").evaluate("node => node.parentElement.parentElement.id") == "legacy-portfolio-owner"
        assert page.locator("#work-editor").evaluate("node => node.parentElement.id") == "legacy-work-owner"
        browser.close()
