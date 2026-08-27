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
from natureai_next.server.knowledge_review_web import patch_knowledge_review_web_response
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
        patch_knowledge_review_web_response,
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


def test_web043_patch_uses_governed_proposal_and_removes_false_analysis_action() -> None:
    response = patch_knowledge_review_web_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")

    assert "Submit identification proposal" in script
    assert 'subject:{type:"observation",id:observationId}' in script
    assert 'candidate:{type:"identification"' in script
    assert "source_snapshot" in script
    assert "Review history" in script
    assert 'byId("run-analysis")?.remove()' in script
    assert 'stateInput.closest("label").remove()' in script
    assert "crypto.randomUUID()" not in script
    assert 'review_state:"accepted"' not in script
    assert 'method:"POST",headers:{"If-Match":String(item.revision||1)}' in script


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_submit_identification_is_server_owned_and_review_remains_revisioned(
    tmp_path: Path,
    browser_name: str,
) -> None:
    proposals: list[dict] = []
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
        elif path == "dossiers":
            payload = {"items": []}
        elif path == "knowledge" and method == "GET":
            payload = {"items": proposals}
        elif path == "knowledge" and method == "POST":
            assert isinstance(body, dict)
            for protected in (
                "id",
                "revision",
                "review_state",
                "submitted_by_identity_id",
                "created_at_us",
                "updated_at_us",
                "status",
            ):
                assert protected not in body
            assert body["project_id"] == "project-1"
            assert body["provider_key"] == "human-field-note"
            assert body["subject"] == {"type": "observation", "id": "obs-1"}
            assert body["candidate"]["type"] == "identification"
            assert body["candidate"]["value"]["scientific_name"] == "Ardea cinerea"
            assert body["candidate"]["value"]["confidence"] == 0.92
            assert body["source_snapshot"]["producer_name"] == "human-field-note"
            assert body["source_snapshot"]["producer_version"] == "unspecified"
            item = {
                "id": "proposal-1",
                **body,
                "submitted_by_identity_id": "researcher-1",
                "review_state": "pending",
                "review_actions": [],
                "canonical": None,
                "revision": 1,
            }
            proposals[:] = [item]
            status = 201
            payload = {"item": item, "revision": 1}
        elif path == "knowledge/proposal-1/review" and method == "POST":
            assert request.headers.get("if-match") == "1"
            assert body == {"action": "accept"}
            current = proposals[0]
            action = {
                "id": "action-1",
                "proposal_id": "proposal-1",
                "action": "accept",
                "from_state": "pending",
                "to_state": "accepted",
                "actor_identity_id": "researcher-1",
            }
            canonical = {
                "id": "canonical-1",
                "subject": current["subject"],
                "candidate": current["candidate"],
                "source_snapshot": current["source_snapshot"],
                "provider_key": current["provider_key"],
                "source_suggestion_public_id": "proposal-1",
                "acceptance_action_public_id": "action-1",
            }
            updated = {
                **current,
                "review_state": "accepted",
                "review_actions": [action],
                "canonical": canonical,
                "revision": 2,
            }
            proposals[:] = [updated]
            payload = {
                "item": updated,
                "revision": 2,
                "action": action,
                "canonical": canonical,
            }
        else:
            payload = {"items": []}
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
            "sessionStorage.setItem('fieldora-session','web043-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.sidebar .nav[data-page="knowledge"]').click()
        page.wait_for_selector("#page-knowledge:not([hidden])")

        assert page.locator("#run-analysis").count() == 0
        assert page.locator("#knowledge-state").count() == 0
        page.locator("#knowledge-project").select_option("project-1")
        page.locator("#knowledge-observation").fill("obs-1")
        page.locator("#knowledge-producer").fill("human-field-note")
        page.locator("#knowledge-name").fill("Ardea cinerea")
        page.locator("#knowledge-confidence").fill("0.92")
        page.get_by_role("button", name="Submit identification proposal").click()
        page.wait_for_selector('[data-knowledge-proposal="proposal-1"]')
        page.get_by_role("button", name="Accept", exact=True).click()
        page.wait_for_function(
            "() => document.querySelector('[data-knowledge-proposal=\"proposal-1\"]')?.textContent.includes('Accepted conclusion')"
        )
        text = page.locator('[data-knowledge-proposal="proposal-1"]').inner_text()
        assert "Review history" in text
        assert "proposal-1" in text
        assert "action-1" in text

        create = next(
            item
            for item in requests
            if item["method"] == "POST" and item["path"] == "knowledge"
        )
        assert set(create["body"]) == {
            "project_id",
            "provider_key",
            "subject",
            "candidate",
            "source_snapshot",
        }
        review = next(
            item
            for item in requests
            if item["method"] == "POST"
            and item["path"] == "knowledge/proposal-1/review"
        )
        assert review["headers"].get("if-match") == "1"

        inventory = page.evaluate("window.__fieldoraAuditVisibleButtons()")
        assert all(item["contract"] for item in inventory), inventory
        browser.close()
