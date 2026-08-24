from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import patch_browser_functionality_response
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.linked_storage_operator_web import (
    patch_linked_storage_operator_web_response,
)
from natureai_next.server.linked_storage_web import patch_linked_storage_web_response
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
        patch_linked_storage_web_response,
        patch_linked_storage_operator_web_response,
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
    request = route.request
    url = request.url
    path = url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    method = request.method
    if path == "me":
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "identity_id": "researcher-1",
                    "display_name": "Researcher",
                    "organization_id": "org-1",
                }
            ),
        )
        return
    if path == "projects":
        route.fulfill(status=200, content_type="application/json", body='{"items":[]}')
        return
    if path == "runtime":
        route.fulfill(
            status=200,
            content_type="application/json",
            body='{"version":"5.4.0","readiness":{"mode":"managed"},"backends":{}}',
        )
        return
    if path in {"dossiers", "media"}:
        route.fulfill(status=200, content_type="application/json", body='{"items":[]}')
        return
    if path == "linked-storage/sources":
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": [
                        {
                            "storage_id": "archive-1",
                            "display_name": "Primary research archive",
                            "read_only": True,
                            "availability": "online",
                        }
                    ],
                    "count": 1,
                }
            ),
        )
        return
    if path == "linked-storage/browse":
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": [
                        {
                            "media_id": "linked:archive-1:object-1",
                            "storage_id": "archive-1",
                            "relative_path": "Amazon/day-01/image.jpg",
                            "filename": "image.jpg",
                            "mime_type": "image/jpeg",
                            "size_bytes": 6,
                            "modified_ns": 123,
                            "state": "available",
                            "sha256": "a" * 64,
                            "thumbnail_state": "missing",
                            "thumbnail_etag": "",
                            "project_id": "project-1",
                            "metadata": {"camera": "trap-7"},
                        }
                    ],
                    "count": 1,
                    "storage_id": "archive-1",
                    "prefix": "Amazon/day-01",
                }
            ),
        )
        return
    if path == "linked-storage/previews" and method == "POST":
        route.fulfill(
            status=202,
            content_type="application/json",
            body='{"queued_media_ids":["linked:archive-1:object-1"],"unavailable_media_ids":[],"queued_count":1}',
        )
        return
    if path == "linked-storage/thumbnail":
        route.fulfill(status=200, content_type="image/jpeg", body=b"managed-thumbnail")
        return
    if path == "linked-storage/ranges" and method == "POST":
        route.fulfill(
            status=202,
            content_type="application/json",
            body='{"request_id":"range-1","state":"pending"}',
        )
        return
    if path == "linked-storage/ranges" and method == "GET":
        route.fulfill(status=206, content_type="application/octet-stream", body=b"ABCDEF")
        return
    if path == "operator/overview":
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "organization_id": "org-1",
                    "checked_at_epoch": 1000,
                    "service_counts": {"active": 1},
                    "stale_service_count": 0,
                    "expiring_certificate_count": 0,
                    "services": [],
                    "storage": [],
                    "jobs": {},
                    "runtime": {},
                    "linked_archives": [
                        {
                            "storage_id": "archive-1",
                            "display_name": "Primary research archive",
                            "read_only": True,
                            "enabled": True,
                            "service_id": "storage-service-1",
                            "service_name": "Archive service",
                            "node_name": "storage-node-1",
                            "service_state": "active",
                            "heartbeat_age_seconds": 18,
                            "stale": False,
                        },
                        {
                            "storage_id": "archive-disabled",
                            "display_name": "Disabled archive",
                            "read_only": True,
                            "enabled": False,
                            "service_id": "storage-service-2",
                            "service_name": "Disabled archive service",
                            "node_name": "storage-node-2",
                            "service_state": "active",
                            "heartbeat_age_seconds": 24,
                            "stale": False,
                        },
                    ],
                    "linked_archive_events": [
                        {
                            "storage_id": "archive-disabled",
                            "actor_id": "operator-1",
                            "event_type": "source_disabled",
                            "occurred_at": "2026-08-24T01:02:03+00:00",
                        },
                        {
                            "storage_id": "archive-1",
                            "actor_id": "storage-service-1",
                            "event_type": "source_registered",
                            "occurred_at": "2026-08-24T00:00:00+00:00",
                        },
                    ],
                }
            ),
        )
        return
    if path.startswith("operator/linked-archives/") and method == "POST":
        parts = path.split("/")
        storage_id, operation = parts[2], parts[3]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "linked_archive": {
                        "storage_id": storage_id,
                        "enabled": operation == "enable",
                    }
                }
            ),
        )
        return
    route.fulfill(status=200, content_type="application/json", body='{"items":[]}')


def test_patch_is_app_only_and_idempotent() -> None:
    base = ApiResponse(200, b"console.log('base');", "text/javascript; charset=utf-8")
    patched = patch_linked_storage_web_response("/app.js", base)
    assert b"Fieldora linked archives" in patched.body
    assert b"/api/v1/linked-storage/sources" in patched.body
    assert b"/api/v1/linked-storage/browse" in patched.body
    assert b"/api/v1/linked-storage/ranges" in patched.body
    assert patch_linked_storage_web_response("/app.js", patched).body == patched.body
    assert patch_linked_storage_web_response("/other.js", base).body == base.body

    operator = patch_linked_storage_operator_web_response("/app.js", base)
    assert b"linked archive ownership" in operator.body
    assert b"operator-linked-archives" in operator.body
    assert b"operator-linked-archive-events" in operator.body
    assert b"/api/v1/operator/linked-archives/" in operator.body
    assert patch_linked_storage_operator_web_response("/app.js", operator).body == operator.body


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_linked_archive_library_browse_preview_original_and_operator_health(
    tmp_path: Path, browser_name: str
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.locator('.nav[data-page="library"]').click()
        page.wait_for_function("document.getElementById('linked-storage-id').value === 'archive-1'")
        source_option = page.locator('#linked-storage-sources option[value="archive-1"]')
        assert "Primary research archive" in source_option.inner_text()
        assert "read only · online" in source_option.inner_text()
        assert "1 linked archive discovered · 1 online." in page.locator(
            "#linked-storage-status"
        ).inner_text()
        page.locator("#linked-storage-prefix").fill("Amazon/day-01")
        page.locator("#linked-storage-browse").click()
        card = page.locator('[data-linked-media="linked:archive-1:object-1"]')
        card.wait_for()
        page.wait_for_selector(
            '[data-linked-thumbnail="linked:archive-1:object-1"]:not([hidden])'
        )
        assert "Amazon/day-01/image.jpg" in card.inner_text()

        card.click()
        assert "trap-7" in page.locator("#linked-storage-detail").inner_text()
        with page.expect_download() as download_info:
            page.locator("#linked-download-original").click()
        download = download_info.value
        assert download.suggested_filename == "image.jpg"
        assert Path(download.path()).read_bytes() == b"ABCDEF"

        page.locator('.nav[data-page="operator"]').click()
        page.wait_for_selector("#operator-linked-archives .row")
        operator_text = page.locator("#operator-linked-archives").inner_text()
        assert "Primary research archive" in operator_text
        assert "Archive service" in operator_text
        assert "active · Healthy" in operator_text
        assert "18s heartbeat age" in operator_text
        assert "Disabled archive" in operator_text
        assert "active · Disabled" in operator_text
        assert "/mnt/" not in operator_text

        page.wait_for_selector("#operator-linked-archive-events .row")
        event_text = page.locator("#operator-linked-archive-events").inner_text()
        assert "source_disabled" in event_text
        assert "archive-disabled · operator-1" in event_text
        assert "source_registered" in event_text
        assert "archive-1 · storage-service-1" in event_text
        assert "root_alias" not in event_text
        assert "/mnt/" not in event_text

        enabled_row = page.locator('[data-linked-archive="archive-1"]')
        with page.expect_request(
            lambda request: request.method == "POST"
            and request.url.endswith("/api/v1/operator/linked-archives/archive-1/disable")
        ):
            enabled_row.locator('[data-linked-archive-action="disable"]').click()
        page.wait_for_timeout(50)
        assert "Linked archive disabled." in page.locator(
            "#operator-linked-archives-status"
        ).inner_text()

        disabled_row = page.locator('[data-linked-archive="archive-disabled"]')
        with page.expect_request(
            lambda request: request.method == "POST"
            and request.url.endswith(
                "/api/v1/operator/linked-archives/archive-disabled/enable"
            )
        ):
            disabled_row.locator('[data-linked-archive-action="enable"]').click()
        page.wait_for_timeout(50)
        assert "Linked archive enabled." in page.locator(
            "#operator-linked-archives-status"
        ).inner_text()
        browser.close()
