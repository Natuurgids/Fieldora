from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.desktop_alignment_web import patch_desktop_alignment_web_response
from natureai_next.server.research_records_web import patch_research_records_response
from natureai_next.server.visible_control_audit_web import (
    patch_visible_control_audit_response,
)

_DOMAINS = (
    "specimens",
    "encounters",
    "protocols",
    "survey-events",
    "enrichments",
    "samples",
    "laboratory-records",
)


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
        patch_desktop_alignment_web_response,
        patch_research_records_response,
        patch_visible_control_audit_response,
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


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_all_research_domains_create_open_and_revision_edit_without_browser_owned_id(
    tmp_path: Path,
    browser_name: str,
) -> None:
    state: dict[str, list[dict]] = {domain: [] for domain in _DOMAINS}
    requests: list[dict[str, object]] = []

    def route_api(route: Route) -> None:
        request = route.request
        tail = request.url.split("/api/v1/", 1)[-1]
        path = tail.split("?", 1)[0]
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        requests.append(
            {
                "method": method,
                "path": path,
                "headers": request.headers,
                "body": body,
            }
        )
        status = 200
        if path == "me":
            payload: object = {
                "identity_id": "researcher-1",
                "display_name": "Researcher",
                "organization_id": "org-1",
            }
        elif path == "projects":
            payload = {"items": [{"id": "project-1", "name": "Wetland"}]}
        elif path == "runtime":
            payload = {
                "version": "5.4.0",
                "readiness": {"mode": "managed"},
                "backends": {},
            }
        elif path in {"dossiers", "collections"}:
            payload = {"items": []}
        else:
            parts = path.split("/")
            domain = parts[0]
            if domain not in state:
                payload = {"items": []}
            elif len(parts) == 1 and method == "GET":
                payload = {"items": state[domain], "count": len(state[domain])}
            elif len(parts) == 1 and method == "POST":
                assert isinstance(body, dict)
                assert "id" not in body
                assert "revision" not in body
                assert "recorded_by" not in body
                assert "recorded_at" not in body
                item = {
                    "id": f"{domain}-{len(state[domain]) + 1}",
                    "organization_id": "org-1",
                    "record_type": domain,
                    **body,
                    "revision": 1,
                }
                state[domain].append(item)
                status = 201
                payload = {"item": item, "revision": 1}
            else:
                record_id = parts[1]
                item = next(value for value in state[domain] if value["id"] == record_id)
                if method == "GET":
                    payload = {"item": item, "revision": item["revision"]}
                elif method == "PATCH":
                    assert request.headers.get("if-match") == str(item["revision"])
                    assert isinstance(body, dict)
                    assert "project_id" not in body
                    item.update(body)
                    item["revision"] += 1
                    payload = {"item": item, "revision": item["revision"]}
                else:
                    status = 405
                    payload = {"error": "method_not_allowed"}
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(payload),
        )

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", route_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','web042-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.sidebar .nav[data-page="research"]').click()
        page.wait_for_selector("#page-research:not([hidden])")

        for domain in _DOMAINS:
            page.locator(f'[data-research-domain="{domain}"]').click()
            page.get_by_role("button", name="New research record", exact=False).click()
            page.locator("#science-project").select_option("project-1")
            page.locator("#science-name").fill(f"{domain} record")
            page.locator("#science-status").fill("active")
            page.locator("#science-parent").fill("parent-1")
            page.locator("#science-description").fill(f"Governed {domain} description")
            page.locator("#science-save").click()
            page.wait_for_selector(f'[data-research-record="{domain}-1"]')

        creates = [
            item
            for item in requests
            if item["method"] == "POST" and item["path"] in _DOMAINS
        ]
        assert [item["path"] for item in creates] == list(_DOMAINS)
        assert all(item["body"]["project_id"] == "project-1" for item in creates)

        page.locator('[data-research-domain="specimens"]').click()
        page.wait_for_selector('[data-research-record="specimens-1"]')
        page.locator('[data-research-record="specimens-1"]').click()
        page.wait_for_function(
            "() => document.querySelector('#science-save')?.textContent.includes('Update')"
        )
        assert page.locator("#science-project").is_disabled()
        assert "specimens-1" in page.locator("#research-record-detail").inner_text()
        page.locator("#science-description").fill("Reviewed voucher description")
        page.locator("#science-save").click()
        page.wait_for_function(
            "() => document.querySelector('[data-research-record=\"specimens-1\"]')?.textContent.includes('rev 2')"
        )

        patch = next(
            item
            for item in requests
            if item["method"] == "PATCH" and item["path"] == "specimens/specimens-1"
        )
        assert patch["headers"].get("if-match") == "1"
        assert patch["body"]["description"] == "Reviewed voucher description"
        assert "project_id" not in patch["body"]

        inventory = page.evaluate("window.__fieldoraAuditVisibleButtons()")
        assert all(item["contract"] for item in inventory), inventory
        browser.close()
