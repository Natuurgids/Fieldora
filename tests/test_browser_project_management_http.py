from __future__ import annotations

import contextlib
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

from natureai_next.domain.access_control import AccessDecision, AccessRequest, Identity, IdentityKind
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.http import handler_for
from natureai_next.server.postgres_project_management import PostgresProjectManagementService


class _Authentication:
    def __init__(self, organization_id: str) -> None:
        self.identity = Identity(
            "browser-project-user",
            IdentityKind.USER,
            "Project Creator",
            organization_id,
            attributes={"platform_admin": "true"},
        )

    def authenticate(self, token: str) -> Identity:
        assert token == "browser-token"
        return self.identity


class _Decisions:
    def __init__(self) -> None:
        self.requests: list[AccessRequest] = []

    def decide(self, request: AccessRequest) -> AccessDecision:
        self.requests.append(request)
        return AccessDecision(True, "test")


class _Science:
    def records(self, _collection: str) -> tuple[dict, ...]:
        return ()

    def put(self, _collection: str, _record: dict, _expected_revision: int | None) -> int:
        raise AssertionError("managed browser project creation must not write Science snapshots")


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


@contextlib.contextmanager
def _managed_browser_server(organization_id: str):
    project_management = PostgresProjectManagementService(_connect_factory())
    decisions = _Decisions()
    api = BrowserFunctionalityFieldoraApi(
        _Authentication(organization_id),
        decisions,
        _Science(),
        Path("src/natureai_next/resources/server_web"),
    )
    api._project_management = project_management
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(api))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_port}/",
            project_management,
            decisions,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.integration
def test_create_project_click_persists_authoritative_postgres_project() -> None:
    organization_id = f"browser-org-{uuid4()}"
    with _managed_browser_server(organization_id) as (
        url,
        project_management,
        decisions,
    ), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        failed_requests: list[tuple[str, str, str]] = []
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                (request.method, request.url, request.failure or "unknown")
            ),
        )
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-token')"
        )
        page.goto(url)
        page.locator("#workspace").wait_for(state="visible")
        page.locator('[data-page="projects"]').click()
        page.locator("#page-projects").wait_for(state="visible")
        page.locator("#portfolio-new-project").click()
        page.locator("#portfolio-project-editor").wait_for(state="visible")
        page.locator("#portfolio-project-name").fill("Managed Browser Project")
        page.locator("#portfolio-project-description").fill(
            "Created through the real managed browser click path"
        )

        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/projects")
        ) as response_info:
            page.locator("#portfolio-project-save").click()
        response = response_info.value
        response_payload = response.json()
        request_payload = json.loads(response.request.post_data or "{}")

        page.locator("#portfolio-project-editor").wait_for(state="hidden")
        page.get_by_text("Managed Browser Project", exact=True).first.wait_for(state="visible")

        assert response.status == 201
        canonical_id = response_payload["item"]["id"]
        assert canonical_id
        assert canonical_id != request_payload["id"]
        assert response_payload["item"]["status"] == "active"
        assert response_payload["item"]["owner_id"] == "browser-project-user"
        assert failed_requests == []

        projects = project_management.projects(organization_id)
        assert [item.project_id for item in projects] == [canonical_id]
        assert projects[0].name == "Managed Browser Project"
        assert projects[0].description == "Created through the real managed browser click path"
        assert project_management.member_role(canonical_id, "browser-project-user") == "admin"
        assert [item["name"] for item in project_management.statuses(canonical_id)] == [
            "To Do",
            "In Progress",
            "QA",
            "Blocked",
            "Done",
        ]
        activity = project_management.activity(canonical_id)
        assert len(activity) == 1
        assert activity[0]["actor_id"] == "browser-project-user"
        assert activity[0]["event_type"] == "project.created"
        assert activity[0]["details"] == {"name": "Managed Browser Project"}
        assert any(
            request.action == "create"
            and request.resource_type == "project"
            and request.organization_id == organization_id
            for request in decisions.requests
        )
        browser.close()
