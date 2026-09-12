from __future__ import annotations

from playwright.sync_api import sync_playwright

from natureai_next.server.observation_actions_web import _OBSERVATION_ACTIONS_PATCH


def test_observation_actions_only_mutate_observation_workspace_controls() -> None:
    script = _OBSERVATION_ACTIONS_PATCH.decode("utf-8")

    assert 'const observationsPage=document.getElementById("page-observations")' in script
    assert "observationsPage.querySelector('[data-observation-filter=\"disputed\"]')" in script
    assert "observationsPage.querySelector('[data-observation-decision=\"deferred\"]')" in script
    assert "document.querySelector('[data-observation-filter=" not in script
    assert "document.querySelector('[data-observation-decision=" not in script

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """
            <button id="outside-filter" data-observation-filter="disputed">Outside filter</button>
            <button id="outside-decision" data-observation-decision="deferred">Outside decision</button>
            <section id="page-observations">
              <button id="inside-filter" data-observation-filter="disputed">Disputed</button>
              <button id="inside-decision" data-observation-decision="deferred">Defer</button>
            </section>
            """
        )
        page.add_script_tag(content=script)

        assert page.locator("#inside-filter").get_attribute("data-observation-filter") == "rejected"
        assert page.locator("#inside-filter").inner_text() == "Rejected"
        assert page.locator("#inside-decision").get_attribute("data-observation-decision") == "unconfirmed"
        assert page.locator("#inside-decision").inner_text() == "Return to review"

        assert page.locator("#outside-filter").get_attribute("data-observation-filter") == "disputed"
        assert page.locator("#outside-filter").inner_text() == "Outside filter"
        assert page.locator("#outside-decision").get_attribute("data-observation-decision") == "deferred"
        assert page.locator("#outside-decision").inner_text() == "Outside decision"
        browser.close()
