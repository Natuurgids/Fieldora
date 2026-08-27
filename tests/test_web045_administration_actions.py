from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright

from natureai_next.server import administration_actions_api
from natureai_next.server.administration_actions_api import AdministrationActionsApiMixin
from natureai_next.server.administration_actions_web import (
    patch_administration_actions_response,
)
from natureai_next.server.api import ApiResponse


def test_capability_projection_preserves_exact_operator_verbs(monkeypatch) -> None:
    class Base:
        def dispatch(
            self, method: str, target: str, headers: dict[str, str], body: bytes
        ) -> ApiResponse:
            del method, target, headers, body
            return ApiResponse.json(
                200,
                {
                    "default_deny": True,
                    "pages": {"operator": True, "administration": True},
                    "actions": {"operator.manage": True},
                },
            )

        def _identity(self, headers: dict[str, str]):
            del headers
            return "token", SimpleNamespace(identity_id="operator-1")

    class Api(AdministrationActionsApiMixin, Base):
        pass

    allowed = {"service.drain", "storage.disable"}
    monkeypatch.setattr(
        administration_actions_api,
        "_has_authority",
        lambda _application, _identity, rule: rule[0] in allowed,
    )

    response = Api().dispatch("GET", "/api/v1/web/capabilities", {}, b"")
    actions = json.loads(response.body)["actions"]

    assert actions["operator.manage"] is True
    assert actions["operator.services.drain"] is True
    assert actions["operator.services.activate"] is False
    assert actions["operator.services.stop"] is False
    assert actions["operator.services.revoke"] is False
    assert actions["operator.storage.disable"] is True
    assert actions["operator.storage.enable"] is False


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        """<!doctype html><html><head><style>
        [data-fieldora-authorization-hidden="true"]{display:none!important}
        </style></head><body>
        <button class="nav" data-page="operator">Operator</button>
        <section id="page-operator">
          <div id="operator-services">
            <button data-op="activate">activate</button>
            <button data-op="drain">drain</button>
            <button data-op="stop">stop</button>
            <button data-op="revoke">revoke</button>
          </div>
          <div id="operator-linked-archives">
            <button data-linked-archive-action="enable">Enable archive</button>
            <button data-linked-archive-action="disable">Disable archive</button>
          </div>
        </section>
        <script src="app.js"></script></body></html>""",
        encoding="utf-8",
    )
    base = b"""
    async function api(){
      return {actions:{
       'operator.manage':true,
       'operator.services.activate':false,
       'operator.services.drain':true,
       'operator.services.stop':false,
       'operator.services.revoke':false,
       'operator.storage.enable':false,
       'operator.storage.disable':true
      }};
    }
    """
    response = patch_administration_actions_response(
        "/app.js", ApiResponse(200, base, "text/javascript; charset=utf-8")
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


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_operator_controls_are_filtered_by_exact_authorized_action(
    tmp_path: Path, browser_name: str
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Fail closed before the exact capability projection is resolved.
        assert page.locator('[data-op="activate"]').is_hidden()
        assert page.locator('[data-op="drain"]').is_hidden()

        page.locator('.nav[data-page="operator"]').click()
        page.wait_for_function(
            "() => document.querySelector('[data-op=\"drain\"]')?.dataset.administrationActionVerified === 'true'"
        )

        assert page.locator('[data-op="drain"]').is_visible()
        assert page.locator('[data-op="activate"]').is_hidden()
        assert page.locator('[data-op="stop"]').is_hidden()
        assert page.locator('[data-op="revoke"]').is_hidden()
        assert page.locator('[data-linked-archive-action="disable"]').is_visible()
        assert page.locator('[data-linked-archive-action="enable"]').is_hidden()
        browser.close()
