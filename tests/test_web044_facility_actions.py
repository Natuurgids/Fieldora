from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_api import (
    FacilityActionsApiMixin,
    relocation_action_contract,
)
from natureai_next.server.facility_actions_web import patch_facility_actions_response


def test_relocation_action_contract_is_fail_closed_and_marks_final_placement() -> None:
    assert relocation_action_contract("pending") == {
        "next_actions": ("ready", "removed", "cancelled", "exception"),
        "is_final_placement": False,
        "is_terminal": False,
    }
    assert relocation_action_contract("placed") == {
        "next_actions": ("completed", "exception"),
        "is_final_placement": True,
        "is_terminal": False,
    }
    assert relocation_action_contract("completed") == {
        "next_actions": (),
        "is_final_placement": True,
        "is_terminal": True,
    }
    assert relocation_action_contract("forged-state") == {
        "next_actions": (),
        "is_final_placement": False,
        "is_terminal": True,
    }


def test_facility_action_projection_decorates_campaign_without_dropping_headers() -> None:
    class Base:
        def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> ApiResponse:
            del method, target, headers, body
            return ApiResponse(
                200,
                json.dumps(
                    {
                        "campaign": {
                            "id": "campaign-1",
                            "steps": [
                                {"id": "step-1", "state": "removed"},
                                {"id": "step-2", "state": "completed"},
                            ],
                        }
                    }
                ).encode(),
                headers=(("X-Fieldora-Session", "kept"),),
            )

    class Api(FacilityActionsApiMixin, Base):
        pass

    response = Api().dispatch(
        "GET", "/api/v1/facility-planning/campaigns/campaign-1", {}, b""
    )
    payload = json.loads(response.body)
    first, second = payload["campaign"]["steps"]
    assert first["next_actions"] == ["in_transit", "staging", "exception"]
    assert first["is_final_placement"] is False
    assert second["next_actions"] == []
    assert second["is_terminal"] is True
    assert response.headers == (("X-Fieldora-Session", "kept"),)


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        """<!doctype html><html><body>
        <button class="nav" data-page="operations">Operations</button>
        <p id="facility-planning-status"></p>
        <div id="facility-campaign-detail">
          <div class="row">
            <span class="pill">removed</span>
            <span>
              <button data-step="step-1" data-state="removed">removed</button>
              <button data-step="step-1" data-state="in_transit">in transit</button>
              <button data-step="step-1" data-state="staging">staging</button>
              <button data-step="step-1" data-state="stored">stored</button>
              <button data-step="step-1" data-state="placed">placed</button>
              <button data-step="step-1" data-state="displayed">displayed</button>
              <button data-step="step-1" data-state="completed">completed</button>
              <button data-step="step-1" data-state="exception">exception</button>
            </span>
          </div>
        </div>
        <script src="app.js"></script></body></html>""",
        encoding="utf-8",
    )
    base = b"""
    async function api(path, options={}){
      const response=await fetch(path, options);
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      return response.json();
    }
    """
    patched = patch_facility_actions_response(
        "/app.js", ApiResponse(200, base, "text/javascript; charset=utf-8")
    )
    (tmp_path / "app.js").write_bytes(patched.body)

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
def test_browser_renders_only_server_permitted_relocation_actions(
    tmp_path: Path, browser_name: str
) -> None:
    def route_api(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "step": {
                        "id": "step-1",
                        "state": "removed",
                        "next_actions": ["in_transit", "staging", "exception"],
                        "is_final_placement": False,
                        "is_terminal": False,
                    }
                }
            ),
        )

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/facility-planning/steps/**", route_api)
        page.goto(url)
        page.wait_for_selector('[data-state="in_transit"]:not([hidden])')

        visible = page.locator(
            '#facility-campaign-detail button[data-step]:not([hidden])'
        ).evaluate_all("els => els.map(el => el.dataset.state)")
        assert visible == ["in_transit", "staging", "exception"]
        assert page.locator('[data-state="stored"]').is_hidden()
        assert page.locator('[data-state="placed"]').is_hidden()
        assert page.locator('[data-state="completed"]').is_hidden()
        assert page.locator('[data-state="in_transit"]').get_attribute(
            "data-facility-movement-action"
        ) == "true"
        assert "current placement remains authoritative" in page.locator(
            "#facility-campaign-detail"
        ).inner_text()
        browser.close()
