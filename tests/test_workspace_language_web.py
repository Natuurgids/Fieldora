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
    elif path == "specimens":
        payload = {
            "items": [
                {"id": "specimen-1", "name": "Moss voucher", "status": "active"},
                {"id": "specimen-2", "name": "Lichen voucher", "status": "active"},
            ]
        }
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_workspace_search_language_matches_current_information_architecture(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','workspace-language-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        home_search = page.locator("#page-home input.search")
        assert home_search.is_hidden()

        expectations = {
            "library": ("Search evidence", "Search governed evidence"),
            "observations": ("Search observations", "Search observations"),
            "research": ("Search research records", "Search research records"),
            "knowledge": ("Search knowledge", "Search knowledge and analyses"),
        }
        for workspace, (placeholder, label) in expectations.items():
            page.locator(f'.sidebar .nav[data-page="{workspace}"]').click()
            search = page.locator(f"#page-{workspace} input.search")
            assert search.get_attribute("placeholder") == placeholder
            assert search.get_attribute("aria-label") == label

        page.locator('.sidebar .nav[data-page="research"]').click()
        research_search = page.locator("#page-research input.search")
        assert "global-search" not in (research_search.get_attribute("class") or "")
        page.wait_for_selector("#research-domain-list .row")
        assert page.locator("#research-domain-list .row").count() == 2
        research_search.fill("moss")
        assert page.locator("#research-domain-list .row:visible").count() == 1
        assert "Moss voucher" in page.locator("#research-domain-list .row:visible").inner_text()
        research_search.fill("fern")
        assert page.locator("#research-domain-list .row:visible").count() == 0
        assert page.locator("#research-search-empty").is_visible()
        research_search.fill("")
        assert page.locator("#research-domain-list .row:visible").count() == 2
        assert page.locator("#research-search-empty").is_hidden()

        page.locator('.sidebar .nav[data-page="library"]').click()
        assert page.locator("#page-library .go-import").get_attribute("aria-label") == (
            "Import evidence"
        )
        browser.close()
