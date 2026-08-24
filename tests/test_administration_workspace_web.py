from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    response = patch_managed_web_response("/app.js", response)
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


def _mock_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    if path == "me":
        payload: object = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    elif path in {"status", "health/live", "health/ready"}:
        payload = {"version": "5.4.0", "live": True, "ready": True}
    elif path == "operator/overview":
        payload = {
            "service_counts": {},
            "stale_service_count": 0,
            "expiring_certificate_count": 0,
            "services": [],
            "storage": [],
            "jobs": {},
        }
    elif path == "linked-storage/sources":
        payload = {"items": []}
    elif path == "audit":
        payload = {"items": [], "chain_verified": True}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_administration_navigation_is_grouped_without_losing_destinations(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','administration-grouping-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.sidebar .nav[data-page="administration"]').click()

        nav = page.locator("#page-administration .administration-workspace-nav")
        assert nav.is_visible()
        groups = nav.locator(".administration-nav-group")
        assert groups.count() == 3
        assert groups.locator(".administration-nav-group-label").all_inner_texts() == [
            "Governance & review",
            "Operations",
            "Platform services",
        ]
        assert groups.nth(0).locator("button").all_inner_texts() == [
            "Governance",
            "Intake & Review",
            "Reference Data",
        ]
        assert groups.nth(1).locator("button").all_inner_texts() == [
            "Assets & Facilities",
            "Connectors",
        ]
        assert groups.nth(2).locator("button").all_inner_texts() == [
            "AI Platform",
            "Operator",
            "Platform",
        ]
        assert nav.locator("button").count() == 8

        nav.get_by_role("button", name="Assets & Facilities", exact=True).click()
        assert page.locator("#page-operations").is_visible()
        assert (
            page.locator('.sidebar .nav[data-page="administration"]').get_attribute(
                "aria-selected"
            )
            == "true"
        )
        operations_nav = page.locator(
            "#page-operations .administration-workspace-nav"
        )
        assert operations_nav.locator("button").count() == 8
        assert (
            operations_nav.get_by_role(
                "button", name="Assets & Facilities", exact=True
            ).get_attribute("aria-selected")
            == "true"
        )
        browser.close()
