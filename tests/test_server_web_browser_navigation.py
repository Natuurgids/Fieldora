from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, sync_playwright

from natureai_next.server.api import ApiResponse
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
    request_url = route.request.url
    path = request_url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    payload: object
    if path == "me":
        payload = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "projects":
        payload = {
            "items": [
                {
                    "id": "project-1",
                    "name": "Navigation Test Project",
                    "status": "active",
                    "description": "Browser wiring certification",
                    "owner_id": "admin-1",
                    "budget": 1000,
                }
            ]
        }
    elif path == "phases":
        payload = {
            "items": [
                {
                    "id": "phase-1",
                    "project_id": "project-1",
                    "name": "Field phase",
                    "status": "active",
                    "starts_at": "2026-01-01",
                    "ends_at": "2026-02-01",
                }
            ]
        }
    elif path == "tasks":
        payload = {
            "items": [
                {
                    "id": "task-1",
                    "project_id": "project-1",
                    "phase_id": "phase-1",
                    "name": "Survey task",
                    "status": "active",
                    "assignee_id": "admin-1",
                    "manual_estimate": 8,
                    "realized": 3,
                    "starts_at": "2026-01-05",
                    "ends_at": "2026-01-06",
                },
                {
                    "id": "task-2",
                    "project_id": "project-1",
                    "phase_id": "phase-1",
                    "name": "Review task",
                    "status": "review",
                    "assignee_id": "reviewer-1",
                    "manual_estimate": 4,
                    "realized": 1,
                },
            ]
        }
    elif path == "sprints":
        payload = {"items": []}
    elif path == "runtime":
        payload = {
            "version": "5.4.0",
            "readiness": {"mode": "managed"},
            "backends": {},
        }
    elif path == "media":
        payload = {
            "items": [
                {
                    "media_id": "photo-1",
                    "mime_type": "image/jpeg",
                    "size_bytes": 1024,
                    "project_id": "project-1",
                    "sha256": "a" * 64,
                },
                {
                    "media_id": "sound-1",
                    "mime_type": "audio/wav",
                    "size_bytes": 1024,
                    "project_id": "project-1",
                    "sha256": "b" * 64,
                },
                {
                    "media_id": "video-1",
                    "mime_type": "video/mp4",
                    "size_bytes": 1024,
                    "project_id": "project-1",
                    "sha256": "c" * 64,
                },
                {
                    "media_id": "document-1",
                    "mime_type": "application/pdf",
                    "size_bytes": 1024,
                    "project_id": "project-1",
                    "sha256": "d" * 64,
                },
            ]
        }
    elif path == "observations":
        payload = {
            "items": [
                {"id": "obs-confirmed", "name": "Confirmed bird", "status": "confirmed"},
                {"id": "obs-review", "name": "Review beetle", "status": "needs_review"},
                {"id": "obs-disputed", "name": "Disputed moss", "status": "disputed"},
            ]
        }
    elif path == "knowledge":
        payload = {
            "items": [
                {
                    "id": "knowledge-review",
                    "identification": "Pending Result",
                    "producer": "model-a",
                    "status": "pending_review",
                    "confidence": 0.7,
                },
                {
                    "id": "knowledge-accepted",
                    "identification": "Accepted Result",
                    "producer": "expert",
                    "status": "accepted",
                    "confidence": 1.0,
                },
            ]
        }
    elif path.startswith("operations/"):
        domain = path.split("/", 1)[1]
        payload = {
            "items": [
                {
                    "id": f"{domain}-1",
                    "name": f"{domain.title()} record",
                    "project_id": "project-1",
                    "status": "active",
                }
            ]
        }
    elif path in {
        "specimens",
        "encounters",
        "protocols",
        "survey-events",
        "enrichments",
        "samples",
        "laboratory-records",
    }:
        payload = {
            "items": [
                {
                    "id": f"{path}-1",
                    "project_id": "project-1",
                    "name": f"{path} record",
                    "status": "active",
                }
            ]
        }
    elif path == "admin/contracts":
        payload = {
            "items": [
                {
                    "contract_id": "contract-1",
                    "title": "Main Contract",
                    "organization_id": "local",
                    "status": "active",
                    "starts_at_utc": "2026-01-01T00:00:00Z",
                    "ends_at_utc": "2027-01-01T00:00:00Z",
                    "terms": {"project_id": "project-1"},
                }
            ]
        }
    elif path == "admin/contract-approvals":
        payload = {
            "items": [
                {
                    "contract_id": "contract-approval",
                    "title": "Approval Contract",
                    "organization_id": "local",
                    "status": "proposed",
                    "starts_at_utc": "2026-01-01T00:00:00Z",
                    "ends_at_utc": "2027-01-01T00:00:00Z",
                    "terms": {"project_id": "project-1"},
                }
            ]
        }
    elif path == "admin/contract-expiry":
        payload = {
            "items": [
                {
                    "contract_id": "contract-expiring",
                    "title": "Expiring Contract",
                    "organization_id": "local",
                    "status": "active",
                    "starts_at_utc": "2026-01-01T00:00:00Z",
                    "ends_at_utc": "2026-09-01T00:00:00Z",
                    "terms": {"project_id": "project-1"},
                }
            ]
        }
    elif path == "status":
        payload = {"version": "5.4.0"}
    elif path == "health/live":
        payload = {"live": True}
    elif path == "health/ready":
        payload = {"ready": True}
    elif path == "audit":
        payload = {"items": [], "chain_verified": True}
    elif path == "help":
        payload = {"items": []}
    elif path.startswith("help/"):
        payload = {"title": "Help", "content": "Test help"}
    elif path == "operator/overview":
        payload = {
            "service_counts": {},
            "stale_service_count": 0,
            "expiring_certificate_count": 0,
            "services": [],
            "storage": [],
            "jobs": {},
        }
    elif path == "access-barriers":
        payload = {"contract": None, "signatures": []}
    elif path.startswith("access-barriers/evidence/"):
        payload = {"owner_contract": None}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _assert_page(page: Page, name: str) -> None:
    page.locator(f'.nav[data-page="{name}"]').click()
    page.wait_for_timeout(30)
    assert page.locator(f"#page-{name}").is_visible()
    assert page.evaluate("location.hash") == f"#{name}"


def _click_tab(page: Page, selector: str) -> None:
    tab = page.locator(selector)
    tab.click()
    page.wait_for_timeout(60)
    assert tab.get_attribute("aria-selected") == "true"


def _assert_all_tab_groups(page: Page) -> None:
    _assert_page(page, "library")
    assert page.locator("#media-grid [data-media]").count() == 4
    for filter_name, media_id in (
        ("image", "photo-1"),
        ("audio", "sound-1"),
        ("video", "video-1"),
        ("application", "document-1"),
    ):
        _click_tab(page, f'[data-media-filter="{filter_name}"]')
        assert page.locator("#media-grid [data-media]").count() == 1
        assert page.locator(f'[data-media="{media_id}"]').count() == 1

    _assert_page(page, "observations")
    for filter_name, observation_id in (
        ("confirmed", "obs-confirmed"),
        ("review", "obs-review"),
        ("disputed", "obs-disputed"),
    ):
        _click_tab(page, f'[data-observation-filter="{filter_name}"]')
        assert page.locator("#observation-list [data-observation]").count() == 1
        assert page.locator(f'[data-observation="{observation_id}"]').count() == 1

    _assert_page(page, "projects")
    expected_markers = {
        "hierarchy": "Field phase",
        "kanban": "Survey task",
        "grid": "1 phases",
        "gantt": "2026-01-05",
        "workload": "admin-1",
        "budget": "Budget 1000",
    }
    rendered = set()
    for view, marker in expected_markers.items():
        _click_tab(page, f'[data-portfolio-view="{view}"]')
        page.wait_for_function(
            "view => document.getElementById('portfolio-list').dataset.renderedView === view",
            view,
        )
        text = page.locator("#portfolio-list").inner_text()
        assert marker in text
        rendered.add(text)
    assert len(rendered) == len(expected_markers)

    _assert_page(page, "research")
    for domain in (
        "specimens",
        "encounters",
        "protocols",
        "survey-events",
        "enrichments",
        "samples",
        "laboratory-records",
    ):
        _click_tab(page, f'[data-research-domain="{domain}"]')
        assert f"{domain} record" in page.locator("#research-domain-list").inner_text()

    _assert_page(page, "knowledge")
    _click_tab(page, '[data-knowledge-view="review"]')
    assert "Pending Result" in page.locator("#knowledge-list").inner_text()
    assert "Accepted Result" not in page.locator("#knowledge-list").inner_text()
    assert page.locator("#knowledge-list").get_attribute("data-rendered-view") == "review"
    _click_tab(page, '[data-knowledge-view="accepted"]')
    assert "Accepted Result" in page.locator("#knowledge-list").inner_text()
    assert "Pending Result" not in page.locator("#knowledge-list").inner_text()
    assert page.locator("#knowledge-list").get_attribute("data-rendered-view") == "accepted"

    _assert_page(page, "operations")
    for domain in ("assets", "locations", "drawings", "maintenance", "calibrations"):
        _click_tab(page, f'[data-operations-domain="{domain}"]')
        assert f"{domain.title()} record" in page.locator("#operations-list").inner_text()

    _assert_page(page, "administration")
    assert "Main Contract" in page.locator("#contracts-panel").inner_text()
    _click_tab(page, "#approvals-refresh")
    assert page.locator("#approvals-panel").is_visible()
    assert "Approval Contract" in page.locator("#approvals-panel").inner_text()
    _click_tab(page, "#expiry-refresh")
    assert page.locator("#expiry-panel").is_visible()
    assert "Expiring Contract" in page.locator("#expiry-panel").inner_text()
    _click_tab(page, "#contracts-refresh")
    assert page.locator("#contracts-panel").is_visible()


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_all_visible_workspaces_have_browser_routes_tabs_and_cross_screen_navigation(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        names = page.locator(".nav[data-page]").evaluate_all(
            "els => els.map(e => e.dataset.page)"
        )
        assert {
            "home",
            "library",
            "observations",
            "projects",
            "capacity",
            "research",
            "dossiers",
            "knowledge",
            "administration",
            "aiadmin",
            "reference",
            "connectors",
            "platform",
            "operations",
            "help",
            "data-access",
            "intake-review",
            "operator",
        }.issubset(set(names))

        for name in names:
            _assert_page(page, name)

        _assert_page(page, "library")
        _assert_page(page, "projects")
        page.go_back()
        page.wait_for_timeout(30)
        assert page.locator("#page-library").is_visible()
        page.go_forward()
        page.wait_for_timeout(30)
        assert page.locator("#page-projects").is_visible()

        _assert_all_tab_groups(page)

        page.locator('.nav[data-page="projects"]').click()
        page.locator('[data-portfolio-view="hierarchy"]').click()
        page.wait_for_selector('#portfolio-list [data-kind="project"]')
        page.locator('#portfolio-list [data-kind="project"]').first.click()
        page.get_by_role("button", name="Open project workspace").click()
        assert page.locator("#page-research").is_visible()
        assert "Navigation Test Project" in page.locator("#project-detail").inner_text()

        page.locator('.nav[data-page="operations"]').click()
        page.locator('[data-operations-domain="assets"]').click()
        page.wait_for_selector('[data-operations-id="assets-1"]')
        page.locator('[data-operations-id="assets-1"]').click()
        page.get_by_role("button", name="Open related project").click()
        assert page.locator("#page-research").is_visible()
        assert "Navigation Test Project" in page.locator("#project-detail").inner_text()

        browser.close()
