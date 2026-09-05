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
from natureai_next.server.observation_actions_web import patch_observation_actions_response
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response
from natureai_next.server.visible_control_audit_web import (
    patch_visible_control_audit_response,
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
        patch_science_workflow_web_response,
        patch_observation_actions_response,
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


def _observation(revision: int = 1, state: str = "unconfirmed") -> dict:
    return {
        "id": "observation-1",
        "project_id": "project-1",
        "asset_id": "asset-primary",
        "supporting_asset_ids": [],
        "observation_type": "organism",
        "count": 2,
        "life_stage": None,
        "sex": None,
        "behavior": None,
        "notes": "initial",
        "confirmation_state": state,
        "revision": revision,
    }


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_observation_workspace_actions_use_revisioned_governed_contracts(
    tmp_path: Path,
    browser_name: str,
) -> None:
    state = {"item": _observation(), "created": 0}
    requests: list[dict[str, object]] = []

    def route_api(route: Route) -> None:
        request = route.request
        path = request.url.split("/api/v1/", 1)[-1]
        path_only = path.split("?", 1)[0]
        method = request.method
        headers = request.headers
        body = json.loads(request.post_data) if request.post_data else None
        requests.append(
            {
                "method": method,
                "path": path,
                "headers": headers,
                "body": body,
            }
        )

        status = 200
        if path_only == "me":
            payload: object = {
                "identity_id": "researcher-1",
                "display_name": "Researcher",
                "organization_id": "org-1",
            }
        elif path_only == "projects":
            payload = {"items": [{"id": "project-1", "name": "Wetland"}]}
        elif path_only == "runtime":
            payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
        elif path_only == "dossiers":
            payload = {"items": []}
        elif path_only == "observations" and method == "GET":
            payload = {"items": [state["item"]]}
        elif path_only == "observations" and method == "POST":
            state["created"] = int(state["created"]) + 1
            status = 201
            payload = {
                "item": {
                    "id": f"created-{state['created']}",
                    **body,
                    "supporting_asset_ids": [],
                    "confirmation_state": "unconfirmed",
                    "revision": 1,
                },
                "revision": 1,
            }
        elif path.startswith("media?"):
            payload = {
                "items": [
                    {"media_id": "asset-primary", "mime_type": "image/jpeg"},
                    {"media_id": "asset-2", "mime_type": "image/jpeg"},
                ]
            }
        elif path_only == "media":
            payload = {"items": []}
        elif path_only == "observations/observation-1" and method == "PATCH":
            current = dict(state["item"])
            current.update(body or {})
            current["revision"] = int(current["revision"]) + 1
            state["item"] = current
            payload = {"item": current, "revision": current["revision"]}
        elif path_only == "observations/observation-1/evidence" and method == "POST":
            current = dict(state["item"])
            current["supporting_asset_ids"] = [str((body or {})["asset_id"])]
            current["revision"] = int(current["revision"]) + 1
            state["item"] = current
            payload = {"item": current, "revision": current["revision"]}
        elif path_only == "observations/observation-1/evidence/asset-2" and method == "DELETE":
            current = dict(state["item"])
            current["supporting_asset_ids"] = []
            current["revision"] = int(current["revision"]) + 1
            state["item"] = current
            payload = {"item": current, "revision": current["revision"]}
        else:
            payload = {"items": []}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", route_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','web041-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.sidebar .nav[data-page="observations"]').click()
        page.wait_for_selector("#observation-review-panel:not([hidden])")

        assert page.locator("[data-observation-filter]").all_inner_texts() == [
            "All records",
            "Confirmed",
            "Needs review",
            "Rejected",
        ]
        assert page.locator("[data-observation-decision]").all_inner_texts() == [
            "Accept selected",
            "Reject selected",
            "Return to review",
        ]

        page.get_by_role("button", name="Rejected", exact=True).click()
        assert page.locator("#observation-list [data-observation]").count() == 0
        page.get_by_role("button", name="All records", exact=True).click()
        assert page.locator("#observation-list [data-observation]").count() == 1

        checkbox = page.locator('[data-observation-select="observation-1"]')
        checkbox.check()
        page.get_by_role("button", name="Accept selected", exact=True).click()
        page.wait_for_function(
            "() => document.querySelector('#observation-list .pill')?.textContent.includes('confirmed')"
        )
        review_request = next(
            item
            for item in requests
            if item["method"] == "PATCH"
            and item["path"] == "observations/observation-1"
            and item["body"] == {"confirmation_state": "confirmed"}
        )
        assert review_request["headers"].get("if-match") == "1"

        page.locator('#observation-list [data-observation="observation-1"]').click()
        page.wait_for_selector("#observation-editor:not([hidden])")
        assert page.locator("#observation-editor-title").inner_text() == "Edit observation"
        page.locator("#obs-notes").fill("edited in browser")
        page.get_by_role("button", name="Save observation", exact=True).click()
        page.wait_for_selector("#observation-review-panel:not([hidden])")
        edit_request = next(
            item
            for item in requests
            if item["method"] == "PATCH"
            and item["path"] == "observations/observation-1"
            and isinstance(item["body"], dict)
            and item["body"].get("notes") == "edited in browser"
        )
        assert edit_request["headers"].get("if-match") == "2"

        page.locator('#observation-list [data-observation="observation-1"]').click()
        page.wait_for_selector("#obs-supporting-panel:not([hidden])")
        page.locator("#obs-supporting-select").select_option("asset-2")
        page.get_by_role("button", name="Link evidence", exact=True).click()
        page.wait_for_selector('[data-unlink-evidence="asset-2"]')
        link_request = next(
            item
            for item in requests
            if item["method"] == "POST"
            and item["path"] == "observations/observation-1/evidence"
        )
        assert link_request["body"] == {"asset_id": "asset-2"}
        assert link_request["headers"].get("if-match") == "3"

        page.locator('[data-unlink-evidence="asset-2"]').click()
        page.wait_for_function(
            "() => !document.querySelector('[data-unlink-evidence=\"asset-2\"]')"
        )
        unlink_request = next(
            item
            for item in requests
            if item["method"] == "DELETE"
            and item["path"] == "observations/observation-1/evidence/asset-2"
        )
        assert unlink_request["headers"].get("if-match") == "4"

        page.locator('#observation-workspace-nav [data-task-view="create"]').click()
        page.wait_for_selector("#observation-editor:not([hidden])")
        page.locator("#obs-asset").select_option("asset-primary")
        page.locator("#obs-type").select_option("habitat")
        page.locator("#obs-notes").fill("new habitat observation")
        page.get_by_role("button", name="Save observation", exact=True).click()
        create_request = next(
            item
            for item in requests
            if item["method"] == "POST" and item["path"] == "observations"
        )
        assert create_request["body"]["project_id"] == "project-1"
        assert create_request["body"]["asset_id"] == "asset-primary"
        assert create_request["body"]["observation_type"] == "habitat"

        inventory = page.evaluate("window.__fieldoraAuditVisibleButtons()")
        assert all(item["contract"] for item in inventory), inventory
        browser.close()
