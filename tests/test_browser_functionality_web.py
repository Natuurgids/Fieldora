from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import (
    patch_browser_functionality_response,
)
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.web_compatibility import patch_web_response


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
        patch_contract_web_response,
        patch_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
        patch_browser_functionality_response,
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


def _mock_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    method = route.request.method
    if path == "me":
        payload: object = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "projects" and method == "POST":
        payload = {"item": json.loads(route.request.post_data or "{}"), "revision": 1}
    elif path == "projects":
        payload = {
            "items": [
                {
                    "id": "project-1",
                    "name": "Existing Project",
                    "status": "active",
                    "owner_id": "admin-1",
                }
            ]
        }
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    elif path == "dossiers":
        payload = {"items": []}
    elif path == "media":
        payload = {
            "items": [
                {
                    "media_id": "photo-1",
                    "mime_type": "image/jpeg",
                    "size_bytes": 100,
                    "project_id": "",
                    "sha256": "a" * 64,
                    "download_url": "/api/v1/media/photo-1",
                },
                {
                    "media_id": "audio-1",
                    "mime_type": "audio/wav",
                    "size_bytes": 100,
                    "project_id": "",
                    "sha256": "b" * 64,
                    "download_url": "/api/v1/media/audio-1",
                },
                {
                    "media_id": "video-1",
                    "mime_type": "video/mp4",
                    "size_bytes": 100,
                    "project_id": "",
                    "sha256": "c" * 64,
                    "download_url": "/api/v1/media/video-1",
                },
            ]
        }
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_functional_library_and_project_controls(tmp_path: Path, browser_name: str) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        page.locator('.nav[data-page="library"]').click()
        page.wait_for_selector('#media-grid [data-media="photo-1"] img')
        assert page.locator('#media-grid [data-media="audio-1"] audio[controls]').count() == 1
        assert page.locator('#media-grid [data-media="video-1"] video[controls]').count() == 1
        assert page.locator("#upload-file").get_attribute("multiple") is not None
        assert page.locator("#upload-folder").is_visible()
        assert page.locator("#upload-folder-input").get_attribute("webkitdirectory") is not None

        page.locator('[data-media-filter="video"]').click()
        assert "Videos" in page.locator("#library-view-indicator").inner_text()
        assert page.locator('#media-grid [data-media="video-1"] video[controls]').count() == 1

        page.locator('.nav[data-page="projects"]').click()
        assert page.locator("#portfolio-new-project").is_visible()
        page.locator("#portfolio-new-project").click()
        assert page.locator("#portfolio-project-editor").is_visible()
        page.locator("#portfolio-project-name").fill("Browser Created Project")
        with page.expect_request(lambda request: request.url.endswith("/api/v1/projects") and request.method == "POST") as request_info:
            page.locator("#portfolio-project-save").click()
        sent = json.loads(request_info.value.post_data or "{}")
        assert sent["name"] == "Browser Created Project"
        assert sent["owner_id"] == "admin-1"

        page.locator('[data-portfolio-view="kanban"]').click()
        assert "Kanban view" in page.locator("#portfolio-view-indicator").inner_text()
        browser.close()


def test_recursive_folder_intake_preserves_relative_paths_in_client_contract() -> None:
    source = Path("src/natureai_next/server/browser_functionality_web.py").read_text(
        encoding="utf-8"
    )
    assert 'setAttribute("webkitdirectory","")' in source
    assert "file.webkitRelativePath||file.name" in source
    assert "relative_path:relative" in source
    assert "expected_files:files.length" in source
