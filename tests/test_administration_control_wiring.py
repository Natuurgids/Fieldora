from __future__ import annotations

import contextlib
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.visible_control_audit_web import (
    patch_visible_control_audit_response,
)

ADMINISTRATION_WEB = Path(
    "src/natureai_next/server/administration_management_web.py"
)


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())

    # Production response order: the API composition installs WEB-040 first and the
    # HTTP adapter appends the managed feature modules afterwards. The audit's
    # MutationObserver must therefore see controls created by those later modules.
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    response = patch_visible_control_audit_response("/app.js", response)
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


def _capabilities() -> dict[str, object]:
    pages = {
        name: True
        for name in (
            "home",
            "library",
            "observations",
            "projects",
            "research",
            "research-records",
            "dossiers",
            "capacity",
            "knowledge",
            "administration",
            "governance",
            "audit",
            "operations",
            "intake-review",
            "reference",
            "connectors",
            "aiadmin",
            "operator",
            "platform",
            "help",
        )
    }
    return {
        "default_deny": True,
        "pages": pages,
        "actions": {
            "projects.create": True,
            "library.import": True,
            "aiadmin.manage": True,
            "aiadmin.models.manage": True,
            "aiadmin.providers.manage": True,
            "aiadmin.mcp.manage": True,
            "operator.manage": True,
        },
    }


def _mock_api(route: Route, calls: dict[str, int]) -> None:
    request = route.request
    path = request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    key = f"{request.method} {path}"
    calls[key] = calls.get(key, 0) + 1

    user = {
        "identity_id": "user-1",
        "display_name": "Research User",
        "username": "research.user",
        "enabled": True,
        "roles": ["researcher"],
    }
    if path == "web/capabilities":
        payload: object = _capabilities()
    elif path == "me":
        payload = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "projects":
        payload = {"items": []}
    elif path == "runtime":
        payload = {
            "version": "5.4.0",
            "readiness": {"mode": "managed"},
            "backends": {},
        }
    elif path == "operator/overview":
        payload = {
            "organization_id": "local",
            "service_counts": {},
            "stale_service_count": 0,
            "expiring_certificate_count": 0,
            "services": [],
            "storage": [],
            "linked_archives": [
                {
                    "storage_id": "archive-1",
                    "display_name": "Archive One",
                    "service_id": "storage-service-1",
                    "service_name": "Storage Service",
                    "service_state": "active",
                    "node_name": "node-1",
                    "enabled": True,
                    "stale": False,
                    "read_only": True,
                    "heartbeat_age_seconds": 2,
                }
            ],
            "linked_archive_events": [],
            "jobs": {"by_status": {}, "recent": []},
        }
    elif path == "linked-storage/sources":
        payload = {"items": []}
    elif path == "administration/users" and request.method == "GET":
        payload = {"items": [user], "count": 1}
    elif path == "administration/users" and request.method == "POST":
        payload = {"user": user}
    elif path.startswith("administration/users/user-1/"):
        payload = {"user": user, "reset": True}
    elif path == "audit":
        payload = {"items": [], "chain_verified": True}
    elif path in {"status", "health/live", "health/ready"}:
        payload = {"version": "5.4.0", "live": True, "ready": True}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _assert_all_visible_buttons_wired(page) -> None:
    page.wait_for_timeout(25)
    inventory = page.evaluate("window.__fieldoraAuditVisibleButtons()")
    unwired = [item for item in inventory if not item["contract"]]
    assert not unwired, unwired


def test_administration_module_requires_wiring_for_every_static_button() -> None:
    """A new Administration button must be wired in the same feature module."""
    text = ADMINISTRATION_WEB.read_text(encoding="utf-8")
    declared = set(re.findall(r'<button id="([^"]+)"', text))
    wired = set(re.findall(r'byId\("([^"]+)"\)\.onclick=', text))

    assert declared, "Expected Administration feature buttons to audit."
    assert declared == wired, (
        "Administration buttons must declare their onclick wiring in the same modular "
        f"feature. Missing={sorted(declared - wired)} extra={sorted(wired - declared)}"
    )


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_administration_buttons_are_wired_in_final_managed_ui(
    tmp_path: Path,
    browser_name: str,
) -> None:
    calls: dict[str, int] = {}
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route("**/api/v1/**", lambda route: _mock_api(route, calls))
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','administration-wiring-audit')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.sidebar .nav[data-page="administration"]').click()
        page.wait_for_selector("#administration-organisation-management")
        page.wait_for_selector('[data-administration-user="user-1"]')

        _assert_all_visible_buttons_wired(page)

        # Dynamic user rows must own a real handler, not merely look clickable.
        page.locator('[data-administration-user="user-1"]').click()
        assert page.locator("#administration-user-editor").is_visible()
        _assert_all_visible_buttons_wired(page)

        before = calls.get("GET administration/users", 0)
        page.locator("#administration-users-refresh").click()
        page.wait_for_timeout(25)
        assert calls.get("GET administration/users", 0) > before

        page.locator("#administration-user-name").fill("Second User")
        page.locator("#administration-user-username").fill("second.user")
        page.locator("#administration-user-create-password").fill(
            "temporary-password-123"
        )
        page.locator("#administration-user-create-roles").fill("researcher")
        page.locator("#administration-user-create").click()
        page.wait_for_selector("#administration-user-create-status:text-is('User created.')")
        assert calls.get("POST administration/users", 0) == 1

        page.locator('[data-administration-user="user-1"]').click()
        page.locator("#administration-user-roles").fill("researcher, reviewer")
        page.locator("#administration-user-save-roles").click()
        page.wait_for_selector("#administration-user-edit-status:text-is('Roles updated.')")
        assert calls.get("PUT administration/users/user-1/roles", 0) == 1

        page.locator("#administration-user-password").fill("replacement-password-123")
        page.locator("#administration-user-reset-password").click()
        page.wait_for_selector(
            "#administration-user-edit-status:text-is('Password reset. Existing sessions for this user were revoked.')"
        )
        assert calls.get("POST administration/users/user-1/password", 0) == 1

        page.locator("#administration-user-toggle").click()
        page.wait_for_selector(
            "#administration-user-edit-status:text-is('User deactivated and active sessions revoked.')"
        )
        assert calls.get("POST administration/users/user-1/status", 0) == 1

        page.locator("#administration-storage-tab").click()
        assert page.locator("#administration-storage-panel").is_visible()
        assert not page.locator("#administration-users-panel").is_visible()
        _assert_all_visible_buttons_wired(page)

        before = calls.get("GET operator/overview", 0)
        page.locator("#administration-storage-refresh").click()
        page.wait_for_timeout(25)
        assert calls.get("GET operator/overview", 0) > before

        page.locator("#administration-storage-add").click()
        page.wait_for_selector("#page-operator:not([hidden])")
        _assert_all_visible_buttons_wired(page)

        # Sweep every visible top-level workspace. This turns wiring into a final-DOM
        # contract: a newly introduced visible button fails CI unless its owning module
        # has configured a direct, listener-owned or delegated action contract.
        visible_pages = page.locator(".sidebar .nav").evaluate_all(
            "nodes => nodes.filter(node => node.getClientRects().length > 0)"
            ".map(node => node.dataset.page)"
        )
        for page_name in visible_pages:
            page.locator(f'.sidebar .nav[data-page="{page_name}"]').click()
            page.wait_for_timeout(25)
            _assert_all_visible_buttons_wired(page)

        browser.close()
