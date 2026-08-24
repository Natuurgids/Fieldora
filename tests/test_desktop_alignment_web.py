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
from natureai_next.server.desktop_alignment_web import (
    patch_desktop_alignment_web_response,
)
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.library_collections_web import (
    patch_library_collections_web_response,
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
        patch_browser_functionality_response,
        patch_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
        patch_linked_storage_web_response,
        patch_desktop_alignment_web_response,
        patch_library_collections_web_response,
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
    if path == "me":
        payload: object = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    elif path in {"status", "health/live", "health/ready"}:
        payload = {"version": "5.4.0", "live": True, "ready": True}
    elif path == "operator/overview":
        payload = {
            "service_counts": {},
            "stale_service_count": 0,
            "expiring_certificate_count": 0,
            "services": [],
            "storage": [],
            "jobs": {},
        }
    elif path == "linked-storage/sources":
        payload = {
            "items": [
                {
                    "storage_id": "archive-1",
                    "display_name": "Research archive",
                    "read_only": True,
                    "availability": "online",
                }
            ]
        }
    elif path == "audit":
        payload = {"items": [], "chain_verified": True}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_server_web_matches_desktop_workspace_model_and_single_import_action(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','desktop-alignment-certification')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        labels = [
            "".join(text.split())
            for text in page.locator(".sidebar .nav[data-page]").all_inner_texts()
        ]
        assert labels == [
            "⌂Home",
            "▣Library",
            "◎Observations",
            "⚗Research",
            "◫Knowledge&AI",
            "⚙Administration",
            "?Help&Guides",
        ]

        assert page.locator("#home-science-focus").is_visible()
        assert page.locator("#home-primary-actions").is_visible()
        assert page.locator("#home-primary-actions button").all_inner_texts() == [
            "Browse Library",
            "Review observations",
            "Research records",
            "Knowledge & AI",
        ]
        assert page.locator("#page-home .home-system-context").count() == 1
        assert page.locator("#page-home .home-system-context").get_attribute("open") is None
        page.get_by_role("button", name="Research records", exact=True).click()
        assert page.locator("#page-research").is_visible()

        research_targets = page.locator(
            "#page-research .workspace-subnav button"
        ).all_inner_texts()
        assert research_targets == [
            "Projects & Portfolio",
            "Research records",
            "Dossiers",
            "Capacity",
        ]
        assert page.locator("#research-workspace-intro").is_visible()
        assert page.locator("#research-legacy-projects").is_hidden()
        assert page.locator("#research-legacy-related").is_hidden()
        assert page.locator("#page-research .research-records-card").is_visible()
        assert page.locator("#page-research .research-records-card h2").inner_text() == (
            "Research records"
        )
        assert page.locator("#page-research #collection-list").count() == 0
        page.get_by_role("button", name="Projects & Portfolio").click()
        assert page.locator("#page-projects").is_visible()
        assert (
            page.locator('.sidebar .nav[data-page="research"]').get_attribute(
                "aria-selected"
            )
            == "true"
        )

        page.locator('.sidebar .nav[data-page="administration"]').click()
        admin_targets = page.locator(
            "#page-administration .workspace-subnav button"
        ).all_inner_texts()
        assert admin_targets == [
            "Governance",
            "Assets & Facilities",
            "Intake & Review",
            "AI Platform",
            "Reference Data",
            "Connectors",
            "Operator",
            "Platform",
        ]

        page.locator('.sidebar .nav[data-page="library"]').click()
        assert page.locator("#library-workspace-nav button").all_inner_texts() == [
            "Browse evidence",
            "Linked archives",
            "Import",
        ]
        assert page.locator("#library-browse-panel").is_visible()
        assert page.locator("#linked-storage-card").is_hidden()
        assert page.locator("#import-card").is_hidden()
        assert page.locator("#library-collections-card").is_visible()
        assert page.locator("#library-collections-card h2").inner_text() == (
            "Collections & Datasets"
        )
        assert "without changing its provenance" in page.locator(
            "#library-collections-card"
        ).inner_text()
        assert "Browse governed evidence" in page.locator(
            "#library-workspace-intro"
        ).inner_text()

        page.get_by_role("button", name="Linked archives", exact=True).click()
        assert page.locator("#library-browse-panel").is_hidden()
        assert page.locator("#linked-storage-card").is_visible()
        assert page.locator("#import-card").is_hidden()
        assert page.locator("#library-collections-card").is_hidden()
        assert "authoritative storage" in page.locator(
            "#library-workspace-intro"
        ).inner_text()

        page.get_by_role("button", name="Browse evidence", exact=True).click()
        import_button = page.locator("#page-library .go-import")
        assert import_button.inner_text() == "＋ Import"
        import_button.click()
        assert page.locator("#fieldora-import-menu").is_visible()
        assert page.locator("#fieldora-import-menu button").all_inner_texts() == [
            "Files…",
            "Folder with subfolders…",
        ]
        assert page.locator("#upload-folder").count() == 0
        assert page.locator("#upload-file").is_hidden()

        page.get_by_role("button", name="Import", exact=True).click()
        assert page.locator("#library-browse-panel").is_hidden()
        assert page.locator("#linked-storage-card").is_hidden()
        assert page.locator("#import-card").is_visible()
        assert "Choose Files or Folder from Import." in page.locator(
            "#import-source-summary"
        ).inner_text()
        browser.close()
