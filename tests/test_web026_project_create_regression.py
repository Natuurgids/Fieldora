from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import patch_browser_functionality_response


@contextlib.contextmanager
def _browser_fixture(tmp_path: Path, *, patched: bool):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    if patched:
        response = patch_browser_functionality_response("/app.js", response)
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
    method = route.request.method
    if path == "me":
        payload: object = {
            "identity_id": "creator-1",
            "display_name": "Project Creator",
            "organization_id": "org-1",
        }
    elif path == "projects" and method == "POST":
        record = json.loads(route.request.post_data or "{}")
        payload = {
            "item": {
                "id": "server-project-1",
                "name": record["name"],
                "status": "active",
                "owner_id": "creator-1",
                "description": record.get("description", ""),
                "start_date": record.get("start_date", ""),
                "due_date": record.get("due_date", ""),
                "budget": record.get("budget", 0),
                "currency": record.get("currency", "EUR"),
                "revision": 1,
            },
            "revision": 1,
        }
    elif path == "projects":
        payload = {"items": []}
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def test_projects_create_action_is_missing_before_browser_functionality_patch(tmp_path: Path) -> None:
    """Characterize the reported pre-fix Projects & Portfolio failure."""
    with _browser_fixture(tmp_path, patched=False) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.locator("#page-projects").evaluate("node => { node.hidden = false; }")

        assert page.locator("#portfolio-new-project").count() == 0
        assert page.locator("#page-projects .top button").all_inner_texts() == ["Refresh"]
        browser.close()


def test_actual_projects_create_control_opens_editor_and_posts_project(tmp_path: Path) -> None:
    with _browser_fixture(tmp_path, patched=True) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script("sessionStorage.setItem('fieldora-session','browser-token')")
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.nav[data-page="projects"]').click()
        page.locator("#page-projects").wait_for(state="visible")

        create = page.locator("#portfolio-new-project")
        assert create.is_visible()
        create.click()
        page.locator("#portfolio-project-editor").wait_for(state="visible")
        page.locator("#portfolio-project-name").fill("Recovered Project Create")

        with page.expect_request(
            lambda request: request.method == "POST"
            and request.url.endswith("/api/v1/projects")
        ) as request_info:
            page.locator("#portfolio-project-save").click()

        payload = json.loads(request_info.value.post_data or "{}")
        assert payload["name"] == "Recovered Project Create"
        assert "owner_id" not in payload
        assert "status" not in payload
        browser.close()
