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


def test_operator_overview_projects_actions_per_resource() -> None:
    class Base:
        def dispatch(
            self, method: str, target: str, headers: dict[str, str], body: bytes
        ) -> ApiResponse:
            del method, headers, body
            assert target == "/api/v1/operator/overview"
            return ApiResponse(
                200,
                json.dumps(
                    {
                        "services": [
                            {"service_id": "service-1"},
                            {"service_id": "service-2"},
                        ],
                        "linked_archives": [
                            {"storage_id": "archive-1"},
                            {"storage_id": "archive-2"},
                        ],
                    }
                ).encode(),
                headers=(("X-Fieldora-Session", "kept"),),
            )

        def _identity(self, headers: dict[str, str]):
            del headers
            return "token", SimpleNamespace(identity_id="operator-1")

        def _allow_operator(
            self, _identity, _headers: dict[str, str], action: str, resource_id: str
        ) -> bool:
            return (action, resource_id) in {
                ("service.drain", "service-1"),
                ("service.activate", "service-2"),
                ("storage.disable", "archive-1"),
                ("storage.enable", "archive-2"),
            }

    class Api(AdministrationActionsApiMixin, Base):
        pass

    response = Api().dispatch("GET", "/api/v1/operator/overview", {}, b"")
    payload = json.loads(response.body)
    services = {item["service_id"]: item for item in payload["services"]}
    archives = {item["storage_id"]: item for item in payload["linked_archives"]}

    assert services["service-1"]["allowed_actions"] == ["drain"]
    assert services["service-2"]["allowed_actions"] == ["activate"]
    assert archives["archive-1"]["allowed_actions"] == ["disable"]
    assert archives["archive-2"]["allowed_actions"] == ["enable"]
    assert response.headers == (("X-Fieldora-Session", "kept"),)


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        """<!doctype html><html><head><style>
        [data-fieldora-authorization-hidden="true"]{display:none!important}
        </style></head><body>
        <button class="nav" data-page="operator">Operator</button>
        <section id="page-operator">
          <div id="operator-services">
            <button data-op="activate" data-service="service-1">activate 1</button>
            <button data-op="drain" data-service="service-1">drain 1</button>
            <button data-op="stop" data-service="service-1">stop 1</button>
            <button data-op="revoke" data-service="service-1">revoke 1</button>
            <button data-op="activate" data-service="service-2">activate 2</button>
            <button data-op="drain" data-service="service-2">drain 2</button>
          </div>
          <div id="operator-linked-archives">
            <button data-linked-archive-action="enable" data-linked-storage-id="archive-1">Enable archive 1</button>
            <button data-linked-archive-action="disable" data-linked-storage-id="archive-1">Disable archive 1</button>
            <button data-linked-archive-action="enable" data-linked-storage-id="archive-2">Enable archive 2</button>
            <button data-linked-archive-action="disable" data-linked-storage-id="archive-2">Disable archive 2</button>
          </div>
        </section>
        <script src="app.js"></script></body></html>""",
        encoding="utf-8",
    )
    base = b"""
    async function api(){
      return {
       services:[
        {service_id:'service-1',allowed_actions:['drain']},
        {service_id:'service-2',allowed_actions:['activate']}
       ],
       linked_archives:[
        {storage_id:'archive-1',allowed_actions:['disable']},
        {storage_id:'archive-2',allowed_actions:['enable']}
       ]
      };
    }
    document.querySelector('.nav[data-page="operator"]').onclick=()=>api('/api/v1/operator/overview');
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
def test_operator_controls_are_filtered_by_resource_scoped_authority(
    tmp_path: Path, browser_name: str
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Fail closed before the resource-scoped overview has been resolved.
        assert page.locator('[data-op="activate"][data-service="service-1"]').is_hidden()
        assert page.locator('[data-op="drain"][data-service="service-1"]').is_hidden()

        page.locator('.nav[data-page="operator"]').click()
        page.wait_for_function(
            "() => document.querySelector('[data-op=\"drain\"][data-service=\"service-1\"]')?.dataset.administrationActionVerified === 'true'"
        )

        assert page.locator('[data-op="drain"][data-service="service-1"]').is_visible()
        assert page.locator('[data-op="activate"][data-service="service-1"]').is_hidden()
        assert page.locator('[data-op="stop"][data-service="service-1"]').is_hidden()
        assert page.locator('[data-op="revoke"][data-service="service-1"]').is_hidden()
        assert page.locator('[data-op="activate"][data-service="service-2"]').is_visible()
        assert page.locator('[data-op="drain"][data-service="service-2"]').is_hidden()
        assert page.locator(
            '[data-linked-archive-action="disable"][data-linked-storage-id="archive-1"]'
        ).is_visible()
        assert page.locator(
            '[data-linked-archive-action="enable"][data-linked-storage-id="archive-1"]'
        ).is_hidden()
        assert page.locator(
            '[data-linked-archive-action="enable"][data-linked-storage-id="archive-2"]'
        ).is_visible()
        assert page.locator(
            '[data-linked-archive-action="disable"][data-linked-storage-id="archive-2"]'
        ).is_hidden()
        browser.close()
