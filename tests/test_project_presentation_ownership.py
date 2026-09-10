from __future__ import annotations

from playwright.sync_api import sync_playwright

from natureai_next.server.project_core_module_web import _PROJECT_CORE_MODULE_PATCH
from natureai_next.server.project_facility_workspace_web import (
    _PROJECT_FACILITY_WORKSPACE_PATCH,
)
from natureai_next.server.project_inspector_module_web import _PROJECT_INSPECTOR_MODULE_PATCH
from natureai_next.server.project_selected_record_provider_web import (
    _SELECTED_RECORD_PROVIDER_PATCH,
)
from natureai_next.server.web_module_contract_runtime import _runtime_script


def _install_script(page, script: bytes) -> None:
    page.add_script_tag(content=script.decode("utf-8"))


def test_project_owns_cockpit_and_map_presentation_without_facility_adapter() -> None:
    core_script = _PROJECT_CORE_MODULE_PATCH.decode("utf-8")
    inspector_script = _PROJECT_INSPECTOR_MODULE_PATCH.decode("utf-8")
    facility_script = _PROJECT_FACILITY_WORKSPACE_PATCH.decode("utf-8")

    assert "project-core-cockpit-style" in core_script
    assert "#project-desktop-cockpit .cockpit-pane" in core_script
    assert "#project-desktop-cockpit .inspector-tabs" in core_script
    assert "#project-desktop-cockpit .project-map-stage" in core_script
    assert "facility-map-stage" not in inspector_script
    assert "project-map-stage" in inspector_script

    assert "#page-operations .top" in facility_script
    assert "#facility-desktop-cockpit .cockpit-pane" in facility_script
    assert "#facility-desktop-cockpit .inspector-tabs" in facility_script
    assert ".cockpit-page .top" not in facility_script
    assert "\n  .desktop-cockpit{" not in facility_script
    assert ".main{padding-left:14px" not in facility_script

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<section id="page-projects"><div class="top"><h1>Projects</h1></div></section>'
        )
        _install_script(page, _runtime_script())
        _install_script(page, _SELECTED_RECORD_PROVIDER_PATCH)
        _install_script(page, _PROJECT_FACILITY_WORKSPACE_PATCH)
        _install_script(page, _PROJECT_CORE_MODULE_PATCH)
        _install_script(page, _PROJECT_INSPECTOR_MODULE_PATCH)

        assert page.locator("#project-core-cockpit-style").count() == 1
        assert page.locator("#project-desktop-cockpit").evaluate(
            "node => getComputedStyle(node).display"
        ) == "grid"

        page.evaluate(
            """
            FieldoraModuleContracts.resolve('projects.selected-record.select').select({
              kind:'project',id:'project-1',record:{id:'project-1',name:'Owned project'}
            })
            """
        )
        page.get_by_role("button", name="Map").click()
        assert page.locator("#project-inspector-map .project-map-stage").count() == 1
        assert page.locator("#project-inspector-map .facility-map-stage").count() == 0
        browser.close()
