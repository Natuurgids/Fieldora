from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Page, Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.web_compatibility import patch_web_response


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
        patch_contract_web_response,
        patch_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
    ):
        response = patch("/app.js", response)
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    handler = lambda *args, **kwargs: Handler(*args, directory=str(tmp_path), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _mock_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    payload: object
    if path == "me":
        payload = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "projects":
        payload = {
            "items": [
                {
                    "id": "project-1",
                    "name": "Navigation Test Project",
                    "status": "active",
                    "description": "Browser wiring certification",
                    "owner_id": "admin-1",
                }
            ]
        }
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    elif path == "operations/assets":
        payload = {
            "items": [
                {
                    "id": "asset-1",
                    "name": "Microscope",
                    "project_id": "project-1",
                    "status": "active",
                }
            ]
        }
    elif path == "help":
        payload = {"items": []}
    elif path.startswith("help/"):
        payload = {"title": "Help", "content": "Test help"}
    elif path == "operator/overview":
        payload = {
            "service_counts": {},
            "stale_service_count": 0,
            "expiring_certificate_count": 0,
            "services": [],
            "storage": [],
            "jobs": {},
        }
    elif path == "access-barriers":
        payload = {"contract": None, "signatures": []}
    elif path.startswith("access-barriers/evidence/"):
        payload = {"owner_contract": None}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _assert_page(page: Page, name: str) -> None:
    page.locator(f'.nav[data-page="{name}"]').click()
    page.wait_for_timeout(30)
    assert page.locator(f"#page-{name}").is_visible()
    assert page.evaluate("location.hash") == f"#{name}"


def test_all_visible_workspaces_have_browser_routes_and_cross_screen_navigation(
    tmp_path: Path,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        names = page.locator(".nav[data-page]").evaluate_all(
            "els => els.map(e => e.dataset.page)"
        )
        assert {
            "home",
            "library",
            "observations",
            "projects",
            "capacity",
            "research",
            "dossiers",
            "knowledge",
            "administration",
            "aiadmin",
            "reference",
            "connectors",
            "platform",
            "operations",
            "help",
            "data-access",
            "intake-review",
            "operator",
        }.issubset(set(names))

        for name in names:
            _assert_page(page, name)

        # Browser Back/Forward must restore the actual workspace rather than only visual state.
        _assert_page(page, "library")
        _assert_page(page, "projects")
        page.go_back()
        page.wait_for_timeout(30)
        assert page.locator("#page-library").is_visible()
        page.go_forward()
        page.wait_for_timeout(30)
        assert page.locator("#page-projects").is_visible()

        # Project/portfolio selection must offer a real transition into its project workspace.
        page.locator('.nav[data-page="projects"]').click()
        page.wait_for_selector('#portfolio-list [data-kind="project"]')
        page.locator('#portfolio-list [data-kind="project"]').click()
        page.get_by_role("button", name="Open project workspace").click()
        assert page.locator("#page-research").is_visible()
        assert page.locator("#project-detail").contains_text("Navigation Test Project")

        # Operational records with project context must lead to that project rather than dead-end.
        page.locator('.nav[data-page="operations"]').click()
        page.wait_for_selector('[data-operations-id="asset-1"]')
        page.locator('[data-operations-id="asset-1"]').click()
        page.get_by_role("button", name="Open related project").click()
        assert page.locator("#page-research").is_visible()
        assert page.locator("#project-detail").contains_text("Navigation Test Project")

        browser.close()
