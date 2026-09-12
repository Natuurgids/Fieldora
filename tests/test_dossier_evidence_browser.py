from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_module_web import patch_dossier_module_response
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    response = patch_dossier_module_response("/app.js", response)
    response = patch_modular_shell_response("/app.js", response)
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


def test_dossier_evidence_and_lifecycle_controls_reach_final_dom(tmp_path: Path) -> None:
    linked: list[dict[str, object]] = []
    requests: list[tuple[str, str, object | None]] = []
    dossier: dict[str, object] = {
        "id": "dossier-1",
        "project_id": "project-1",
        "name": "Research dossier",
        "description": "Initial description",
        "dossier_type": "project",
        "owner_id": "user-1",
        "reviewer_id": "",
        "review_status": "draft",
        "review_history": [],
        "status": "active",
    }
    library_item = {
        "media_id": "media-1",
        "project_id": "project-source",
        "mime_type": "image/jpeg",
        "size_bytes": 123,
        "sha256": "abc123",
        "filename": "voucher.jpg",
    }

    def lifecycle_item(action: str, remark: str = "") -> dict[str, object]:
        history = [dict(item) for item in dossier.get("review_history", [])]
        history.append(
            {
                "action": action,
                "actor_id": "user-1",
                "remark": remark,
                "recorded_at_epoch": 1234,
            }
        )
        dossier["review_history"] = history
        return dict(dossier)

    def route_api(route: Route) -> None:
        request = route.request
        path = request.url.split("/api/v1/", 1)[-1]
        path_only = path.split("?", 1)[0]
        method = request.method
        body = json.loads(request.post_data) if request.post_data else None
        requests.append((method, path, body))
        status = 200
        if path_only == "me":
            payload: object = {
                "identity_id": "user-1",
                "display_name": "Researcher",
                "organization_id": "org-1",
            }
        elif path_only == "projects":
            payload = {"items": [{"id": "project-1", "name": "Wetland"}]}
        elif path_only == "runtime":
            payload = {
                "version": "5.4.0",
                "readiness": {"mode": "managed"},
                "backends": {},
            }
        elif path_only == "web/capabilities":
            payload = {
                "pages": {"dossiers": True},
                "actions": {},
                "default_deny": True,
            }
        elif path_only == "dossiers" and method == "GET":
            payload = {"items": [dict(dossier)]}
        elif path_only == "dossier-reviews":
            payload = {"items": []}
        elif path_only == "dossiers/dossier-1" and method == "PATCH":
            assert isinstance(body, dict)
            dossier["name"] = body["name"]
            dossier["description"] = body["description"]
            dossier["updated_by"] = "user-1"
            payload = {"item": dict(dossier), "revision": 4}
        elif path_only == "dossiers/dossier-1/review/defer" and method == "POST":
            assert isinstance(body, dict)
            dossier["reviewer_id"] = body["reviewer_id"]
            dossier["review_status"] = "in_review"
            payload = {
                "item": lifecycle_item("deferred_for_review", str(body.get("remark", ""))),
                "revision": 5,
            }
        elif path_only == "dossiers/dossier-1/review/remark" and method == "POST":
            assert isinstance(body, dict)
            payload = {
                "item": lifecycle_item("review_remark", str(body["remark"])),
                "revision": 6,
            }
        elif path_only == "dossiers/dossier-1/review/return" and method == "POST":
            assert isinstance(body, dict)
            dossier["review_status"] = "returned"
            payload = {
                "item": lifecycle_item("returned_to_observer", str(body.get("remark", ""))),
                "revision": 7,
            }
        elif path_only == "media":
            payload = {"items": [library_item], "count": 1}
        elif path_only == "dossiers/dossier-1/media-links" and method == "GET":
            payload = {"items": list(linked), "count": len(linked)}
        elif path_only == "dossiers/dossier-1/media-links" and method == "POST":
            assert body == {"media_id": "media-1"}
            item = {
                "media_id": "media-1",
                "association_type": "dossier",
                "target_id": "dossier-1",
                "purpose": "research",
                "linked_by": "user-1",
                "linked_at_epoch": 1234,
            }
            linked[:] = [
                {
                    "media_id": "media-1",
                    "mime_type": "image/jpeg",
                    "size_bytes": 123,
                    "sha256": "abc123",
                    "linked_by": "user-1",
                    "linked_at_epoch": 1234,
                }
            ]
            status = 201
            payload = {"item": item}
        elif path_only == "dossiers/dossier-1/media-links/media-1" and method == "DELETE":
            linked.clear()
            status = 204
            payload = None
        else:
            payload = {"items": []}
        route.fulfill(
            status=status,
            content_type="application/json",
            body="" if status == 204 else json.dumps(payload),
        )

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", route_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','dossier-evidence-browser-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.evaluate(
            "window.FieldoraModules.navigate('/dossiers','dossier-evidence-browser-certification','push')"
        )
        page.wait_for_selector("#page-dossiers:not([hidden])")
        page.wait_for_selector('[data-dossier-workspace="dossier-1"]')
        page.locator('[data-dossier-workspace="dossier-1"]').click()

        page.wait_for_selector("#dossier-lifecycle-panel:not([hidden])")
        page.locator("#dossier-lifecycle-name").fill("Research dossier revised")
        page.locator("#dossier-lifecycle-description").fill("Revised description")
        page.locator("#dossier-lifecycle-update").click()
        page.wait_for_function(
            "() => document.querySelector('#dossier-workspace-detail')?.textContent.includes('Research dossier revised')"
        )

        page.locator("#dossier-lifecycle-reviewer").fill("reviewer-1")
        page.locator("#dossier-lifecycle-remark").fill("Please check taxonomy")
        page.locator("#dossier-lifecycle-defer").click()
        page.wait_for_function(
            "() => document.querySelector('#dossier-workspace-detail')?.textContent.includes('in_review')"
        )

        page.locator("#dossier-lifecycle-remark").fill("Add location evidence")
        page.locator("#dossier-lifecycle-remark-action").click()
        page.wait_for_function(
            "() => document.querySelector('#dossier-workspace-detail')?.textContent.includes('review_remark')"
        )

        page.locator("#dossier-lifecycle-remark").fill("Please revise")
        page.locator("#dossier-lifecycle-return").click()
        page.wait_for_function(
            "() => document.querySelector('#dossier-workspace-detail')?.textContent.includes('returned')"
        )

        page.wait_for_selector("#dossier-evidence-panel:not([hidden])")
        page.locator("#dossier-evidence-select").select_option("media-1")
        page.locator("#dossier-evidence-link").click()
        page.wait_for_selector('[data-dossier-evidence="media-1"]')
        evidence_row = page.locator('[data-dossier-evidence="media-1"]')
        assert "media-1" in evidence_row.inner_text()
        assert "abc123" in evidence_row.inner_text()
        assert library_item["media_id"] == "media-1"
        assert library_item["sha256"] == "abc123"

        evidence_row.get_by_role("button", name="Unlink").click()
        page.wait_for_function(
            "() => document.querySelector('#dossier-evidence-list')?.textContent.includes('No Library evidence linked.')"
        )
        assert library_item["media_id"] == "media-1"
        assert library_item["sha256"] == "abc123"

        assert any(method == "PATCH" and path == "dossiers/dossier-1" for method, path, _body in requests)
        assert any(
            method == "POST" and path == "dossiers/dossier-1/review/defer"
            for method, path, _body in requests
        )
        assert any(
            method == "POST" and path == "dossiers/dossier-1/review/remark"
            for method, path, _body in requests
        )
        assert any(
            method == "POST" and path == "dossiers/dossier-1/review/return"
            for method, path, _body in requests
        )
        assert any(
            method == "POST" and path.startswith("dossiers/dossier-1/media-links")
            for method, path, _body in requests
        )
        assert any(
            method == "DELETE" and path == "dossiers/dossier-1/media-links/media-1"
            for method, path, _body in requests
        )
        browser.close()
