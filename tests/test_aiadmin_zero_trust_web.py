from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.aiadmin_zero_trust_web import (
    _AIADMIN_ATTRIBUTE_OPTION_STATE,
    _AIADMIN_RECONCILED_AI_LISTENER,
)
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
    assert _AIADMIN_ATTRIBUTE_OPTION_STATE in response.body
    assert _AIADMIN_RECONCILED_AI_LISTENER in response.body
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread = thread
    server_thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def _model_editor_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    if path == "web/capabilities":
        payload: object = {
            "default_deny": True,
            "pages": {
                "home": True,
                "aiadmin": True,
                "administration": True,
                "help": True,
            },
            "actions": {
                "aiadmin.manage": True,
                "aiadmin.models.manage": True,
                "aiadmin.providers.manage": False,
                "aiadmin.mcp.manage": False,
            },
        }
    elif path == "me":
        payload = {
            "identity_id": "model-editor",
            "display_name": "Model Editor",
            "organization_id": "local",
        }
    elif path in {"ai-providers", "ai-models", "mcp-servers"}:
        payload = {"items": []}
    elif path in {"status", "health/live", "health/ready", "runtime"}:
        payload = {
            "live": True,
            "ready": True,
            "readiness": {"mode": "managed"},
            "backends": {},
        }
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _option_state(selector) -> list[dict[str, object]]:
    return selector.evaluate(
        """select => [...select.options].map(option => ({
            value: option.value,
            disabled: option.disabled,
            hidden: option.hidden,
            disabledAttribute: option.getAttribute('disabled'),
            hiddenAttribute: option.getAttribute('hidden')
        }))"""
    )


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_ai_component_editor_exposes_only_authorized_resource_types(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _model_editor_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','aiadmin-zero-trust-certification')"
        )
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
        page.wait_for_selector("#workspace:not([hidden])")

        page.evaluate("showPage('aiadmin')")
        page.wait_for_selector("#page-aiadmin:not([hidden])")

        selector = page.locator("#ai-record-type")
        assert selector.is_visible()
        assert selector.input_value() == "model"
        state = _option_state(selector)
        provider = selector.locator('option[value="provider"]')
        model = selector.locator('option[value="model"]')
        mcp = selector.locator('option[value="mcp"]')
        assert provider.is_disabled(), state
        assert provider.get_attribute("hidden") is not None, state
        assert not model.is_disabled(), state
        assert model.get_attribute("hidden") is None, state
        assert mcp.is_disabled(), state
        assert mcp.get_attribute("hidden") is not None, state
        assert page.locator("#ai-record-save").is_visible()

        browser.close()
