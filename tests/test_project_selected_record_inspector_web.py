from __future__ import annotations

from playwright.sync_api import sync_playwright

import natureai_next.server.http as http
from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_core_module_web import (
    _PROJECT_CORE_MODULE_PATCH,
    patch_project_core_module_response,
)
from natureai_next.server.project_inspector_module_web import _PROJECT_INSPECTOR_MODULE_PATCH
from natureai_next.server.project_selected_record_provider_web import (
    _SELECTED_RECORD_PROVIDER_PATCH,
)
from natureai_next.server.web_module_contract_runtime import _runtime_script
from natureai_next.server.web_module_contracts import foundation_registry


def _install_script(page, script: bytes) -> None:
    page.add_script_tag(content=script.decode("utf-8"))


def test_context_composition_orders_selected_record_before_context_and_inspector() -> None:
    response = ApiResponse(
        200,
        b"WEB-PROJECT-LIST-PROVIDER\nWEB-MODULE-CONTRACT-RUNTIME\n",
        "text/javascript; charset=utf-8",
    )
    script = patch_project_context_provider_response("/app.js", response).body.decode("utf-8")

    selected = script.index("WEB-PROJECT-SELECTED-RECORD-PROVIDER")
    context = script.index("WEB-PROJECT-CONTEXT-PROVIDER")
    inspector = script.index("WEB-PROJECT-INSPECTOR-MODULE")
    assert selected < context < inspector


def test_production_composes_selected_record_independently_of_context_provider(
    monkeypatch,
) -> None:
    shell = patch_modular_shell_response(
        "/app.js",
        ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8"),
    )
    monkeypatch.setattr(
        http,
        "patch_project_context_provider_response",
        lambda target, response: response,
    )

    script = http.patch_managed_web_response(
        "/app.js", shell, registry=foundation_registry()
    ).body.decode("utf-8")

    assert script.count("WEB-PROJECT-SELECTED-RECORD-PROVIDER") == 1
    assert "WEB-PROJECT-CONTEXT-PROVIDER" not in script


def test_project_core_publishes_selection_without_owning_inspector_dom() -> None:
    script = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    ).body.decode("utf-8")

    assert 'resolve?.("projects.selected-record.select")' in script
    assert 'selection.select({kind,id:String(id),record})' in script
    assert 'selection.select(record?{kind:"project",id:String(record.id),record}:null)' in script
    assert "fieldora:project-selected-record-changed" in script
    assert "workSelection" not in script
    assert "function renderInspector" not in script
    assert "function selectInspector" not in script
    assert 'querySelector(".cockpit-right")' not in script
    assert "project-inspector-metadata" not in script
    assert 'right.id="project-inspector-host"' in script


def test_selected_record_contract_supports_replacement_inspector_without_production_consumer() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<div id="replacement-inspector"></div>')
        _install_script(page, _runtime_script())
        _install_script(page, _SELECTED_RECORD_PROVIDER_PATCH)

        assert page.evaluate(
            "FieldoraModuleContracts.provider('projects.selected-record.select')"
        ) == "projects.core"
        assert page.evaluate(
            "FieldoraModuleContracts.resolve('projects.selected-record.select').current()"
        ) is None

        page.evaluate(
            """
            () => {
              const host=document.getElementById('replacement-inspector');
              document.addEventListener('fieldora:project-selected-record-changed', event => {
                const selection=event.detail?.selection;
                host.textContent=selection ? `${selection.kind}:${selection.id}:${selection.record.name}` : 'none';
              });
              FieldoraModuleContracts.resolve('projects.selected-record.select').select({
                kind:'task',id:'task-1',record:{id:'task-1',name:'Replacement task',status:'active'}
              });
            }
            """
        )

        assert page.locator("#replacement-inspector").inner_text() == (
            "task:task-1:Replacement task"
        )
        assert page.evaluate(
            "Object.isFrozen(FieldoraModuleContracts.resolve('projects.selected-record.select').current())"
        )
        assert page.evaluate(
            "Object.isFrozen(FieldoraModuleContracts.resolve('projects.selected-record.select').current().record)"
        )
        browser.close()


def test_production_inspector_builds_its_surface_inside_project_owned_host() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<section id="page-projects"><div class="top"><h1>Projects</h1></div></section>'
        )
        _install_script(page, _runtime_script())
        _install_script(page, _SELECTED_RECORD_PROVIDER_PATCH)
        _install_script(page, _PROJECT_CORE_MODULE_PATCH)
        _install_script(page, _PROJECT_INSPECTOR_MODULE_PATCH)

        assert page.locator("#project-desktop-cockpit").get_attribute(
            "data-project-owner"
        ) == "projects.core"
        assert page.locator("#project-inspector-host").count() == 1
        assert page.locator("#project-inspector-properties").count() == 1
        assert page.locator("#project-inspector-metadata").count() == 1
        assert page.locator("#project-inspector-map").count() == 1
        assert page.locator("#project-inspector-activity").count() == 1

        page.evaluate(
            """
            FieldoraModuleContracts.resolve('projects.selected-record.select').select({
              kind:'project',id:'project-1',record:{
                id:'project-1',name:'Inspector Project',status:'active',location:'Wetland'
              }
            })
            """
        )

        assert page.locator("#project-cockpit-title").inner_text() == "Inspector Project"
        assert "Inspector Project" in page.locator("#project-inspector-metadata").inner_text()
        assert "Wetland" in page.locator("#project-inspector-map").inner_text()
        assert "active" in page.locator("#project-inspector-activity").inner_text()
        assert page.locator('[data-inspector="properties"]').get_attribute("aria-selected") == "true"
        browser.close()
