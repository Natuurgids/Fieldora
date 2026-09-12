from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.capacity_module_web import patch_capacity_module_response
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_capacity_integration_web import (
    patch_project_capacity_integration_response,
)
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_research_integration_web import (
    patch_project_research_integration_response,
)
from natureai_next.server.research_records_web import patch_research_records_response


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    for patch in (
        patch_project_core_module_response,
        patch_research_records_response,
        patch_capacity_module_response,
        patch_project_research_integration_response,
        patch_project_capacity_integration_response,
        patch_modular_shell_response,
        patch_managed_web_response,
    ):
        response = patch("/app.js", response)
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_project_toolbar_handoffs_preserve_canonical_context_in_final_dom(
    tmp_path: Path,
) -> None:
    requests: list[tuple[str, str, object | None]] = []
    project = {"id": "project-1", "name": "Wetland"}
    research_record = {
        "id": "specimen-1",
        "project_id": "project-1",
        "name": "Marsh specimen",
        "record_type": "specimens",
        "status": "active",
        "revision": 1,
    }
    allocation = {
        "id": "allocation-1",
        "project_id": "project-1",
        "user_id": "user-2",
        "start_date": "2026-09-01",
        "end_date": "",
        "hours_per_week": 12,
        "allocation_percent": 30,
        "role": "Ecologist",
    }

    def route_api(route: Route) -> None:
        request = route.request
        path = request.url.split("/api/v1/", 1)[-1]
        path_only = path.split("?", 1)[0]
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        requests.append((method, path, body))

        if path_only == "me":
            payload: object = {
                "identity_id": "user-1",
                "display_name": "Researcher",
                "organization_id": "org-1",
            }
        elif path_only == "projects":
            payload = {"items": [project]}
        elif path_only == "runtime":
            payload = {
                "version": "5.4.0",
                "readiness": {"mode": "managed"},
                "backends": {},
            }
        elif path_only == "web/capabilities":
            payload = {
                "pages": {
                    "projects": True,
                    "research": True,
                    "capacity": True,
                },
                "actions": {},
                "default_deny": True,
            }
        elif path_only == "specimens":
            payload = {"items": [research_record]}
        elif path_only == "allocations":
            payload = {"items": [allocation]}
        else:
            payload = {"items": []}

        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", route_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','project-cross-module-browser-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        page.evaluate(
            "window.FieldoraModules.navigate('/projects','project-cross-module-browser-certification','push')"
        )
        page.wait_for_selector("#page-projects:not([hidden])")
        page.wait_for_selector("#project-desktop-cockpit")
        page.wait_for_function(
            "() => window.FieldoraModuleContracts?.resolve?.('projects.context.select')?.current?.() === 'project-1'"
        )

        research_button = page.locator(
            '[data-fieldora-extension-key="research.project.open"]'
        )
        capacity_button = page.locator(
            '[data-fieldora-extension-key="capacity.project.open"]'
        )
        research_button.wait_for()
        capacity_button.wait_for()
        assert research_button.inner_text() == "Open research"
        assert capacity_button.inner_text() == "Open capacity"
        assert research_button.get_attribute("data-fieldora-owner-module") == "research.dossiers"
        assert capacity_button.get_attribute("data-fieldora-owner-module") == "capacity"

        requests.clear()
        research_button.click()
        page.wait_for_selector("#page-research:not([hidden])")
        page.wait_for_selector('[data-research-record="specimen-1"]')
        research_row = page.locator('[data-research-record="specimen-1"]')
        assert "Marsh specimen" in research_row.inner_text()
        assert "project-1" in research_row.inner_text()
        assert page.evaluate(
            "window.FieldoraResearchRecords?.currentProject?.()"
        ) == "project-1"
        assert page.evaluate(
            "window.FieldoraModuleContracts?.resolve?.('projects.context.select')?.current?.()"
        ) == "project-1"
        assert any(
            method == "GET" and path == "specimens?project_id=project-1"
            for method, path, _body in requests
        )

        page.evaluate(
            "window.FieldoraModules.navigate('/projects','project-cross-module-browser-certification','push')"
        )
        page.wait_for_selector("#page-projects:not([hidden])")
        page.wait_for_selector(
            '[data-fieldora-extension-key="capacity.project.open"]:not([disabled])'
        )
        requests.clear()

        page.locator('[data-fieldora-extension-key="capacity.project.open"]').click()
        page.wait_for_selector("#page-capacity:not([hidden])")
        page.wait_for_function(
            "() => document.querySelector('#capacity-project-label')?.textContent === 'Project project-1'"
        )
        page.wait_for_selector('[data-capacity-allocation="allocation-1"]')
        allocation_row = page.locator('[data-capacity-allocation="allocation-1"]')
        assert "user-2" in allocation_row.inner_text()
        assert "Ecologist" in allocation_row.inner_text()
        assert page.evaluate("window.FieldoraCapacity?.currentProject?.()") == "project-1"
        assert page.evaluate(
            "window.FieldoraModuleContracts?.resolve?.('projects.context.select')?.current?.()"
        ) == "project-1"
        assert any(
            method == "GET" and path == "allocations?project_id=project-1"
            for method, path, _body in requests
        )
        browser.close()
