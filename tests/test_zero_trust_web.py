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
    response = patch_managed_web_response(
        "/app.js",
        ApiResponse(
            200,
            (resource / "app.js").read_bytes(),
            "text/javascript; charset=utf-8",
        ),
    )
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


def _restricted_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    if path == "web/capabilities":
        payload = {
            "default_deny": True,
            "pages": {
                "home": True,
                "library": True,
                "observations": True,
                "projects": False,
                "research-records": False,
                "research": False,
                "dossiers": False,
                "capacity": False,
                "knowledge": True,
                "governance": False,
                "operations": False,
                "intake-review": False,
                "aiadmin": False,
                "reference": False,
                "connectors": False,
                "operator": False,
                "platform": False,
                "administration": False,
                "help": True,
            },
            "actions": {
                "projects.create": False,
                "library.import": False,
                "aiadmin.manage": False,
                "operator.manage": False,
            },
        }
    elif path == "me":
        payload = {
            "identity_id": "restricted-user",
            "display_name": "Restricted User",
            "organization_id": "local",
        }
    elif path == "runtime":
        payload = {"version": "5", "readiness": {"mode": "managed"}, "backends": {}}
    elif path in {"health/live", "health/ready"}:
        payload = {"live": True, "ready": True}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_unauthorized_workspaces_and_actions_are_absent_and_deep_links_fail_closed(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _restricted_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','restricted-certification-token')"
        )
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")

        assert page.locator('.nav[data-page="library"]').is_visible()
        assert page.locator('.nav[data-page="projects"]').is_hidden()
        assert page.locator('.nav[data-page="administration"]').is_hidden()
        assert page.locator('[data-workspace-target="operator"]').is_hidden()
        assert page.locator(".go-import").first.is_hidden()
        assert page.locator("#portfolio-new-project").is_hidden()

        page.evaluate("showPage('projects')")
        assert page.locator("#page-projects").is_hidden()
        assert page.locator("#page-home").is_visible()
        assert page.evaluate("location.hash") != "#projects"

        page.evaluate("showPage('operator')")
        assert page.locator("#page-operator").is_hidden()
        assert page.locator("#page-home").is_visible()

        browser.close()
