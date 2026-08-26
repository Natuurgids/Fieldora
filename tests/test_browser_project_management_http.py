from __future__ import annotations

import contextlib
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import Page, sync_playwright

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    AccessDecision,
    AccessRequest,
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
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
    def __init__(self, repository: SqliteAccessControlRepository) -> None:
        self.requests: list[AccessRequest] = []
        self._service = PolicyDecisionService(repository)

    def decide(self, request: AccessRequest) -> AccessDecision:
        self.requests.append(request)
        return self._service.decide(request)


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


def _access_repository(
    database_path: Path, identity: Identity
) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(database_path)
    repository.put_identity(identity)
    repository.put_policy(
        Policy(
            policy_id="browser-project-scope",
            name="Browser Project creator scope",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="browser-project-test",
            subject_id=identity.identity_id,
            role_id="",
            actions=("view", "create"),
            resource_types=("project",),
            organization_id=identity.organization_id,
            purposes=("research",),
        )
    )
    return repository


@contextlib.contextmanager
def _managed_browser_server(organization_id: str, access_database: Path):
    project_management = PostgresProjectManagementService(_connect_factory())
    authentication = _Authentication(organization_id)
    access_repository = _access_repository(access_database, authentication.identity)
    decisions = _Decisions(access_repository)
    api = BrowserFunctionalityFieldoraApi(
        authentication,
        decisions,
        _Science(),
        Path("src/natureai_next/resources/server_web"),
        audit_repository=access_repository,
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


def _open_project_editor(page: Page, url: str) -> None:
    page.add_init_script("sessionStorage.setItem('fieldora-session','browser-token')")
    page.goto(url)
    page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
    page.locator("#workspace").wait_for(state="visible")
    page.locator('[data-page="research"]').click()
    page.locator("#page-research").wait_for(state="visible")
    page.locator('#page-research [data-workspace-target="projects"]').click()
    page.locator("#page-projects").wait_for(state="visible")
    page.locator("#portfolio-new-project").click()
    page.locator("#portfolio-project-editor").wait_for(state="visible")


def _project_access_request(
    organization_id: str, project_id: str, action: str
) -> AccessRequest:
    return AccessRequest(
        "browser-project-user",
        action,
        "project",
        project_id,
        organization_id,
        project_id,
        "research",
    )


@pytest.mark.integration
def test_create_project_click_persists_authoritative_postgres_project(tmp_path: Path) -> None:
    organization_id = f"browser-org-{uuid4()}"
    with _managed_browser_server(
        organization_id, tmp_path / "access-control.sqlite3"
    ) as (
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
        _open_project_editor(page, url)
        assert not decisions.decide(
            _project_access_request(organization_id, "not-created-yet", "edit")
        ).allowed
        page.locator("#portfolio-project-name").fill("Managed Browser Project")
        page.locator("#portfolio-project-start-date").fill("2026-09-01")
        page.locator("#portfolio-project-due-date").fill("2026-12-31")
        page.locator("#portfolio-project-budget").fill("1250.50")
        page.locator("#portfolio-project-currency").fill("EUR")
        page.locator("#portfolio-project-description").fill(
            "Created through the real managed browser click path"
        )
        assert page.locator("#portfolio-project-status").count() == 0

        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/projects")
        ) as response_info:
            page.locator("#portfolio-project-save").click()
        response = response_info.value
        response_payload = response.json()
        request_payload = json.loads(response.request.post_data or "{}")
        canonical_id = response_payload["item"]["id"]

        page.locator("#portfolio-project-editor").wait_for(state="hidden")
        page.locator(f'[data-project-tree="{canonical_id}"]').wait_for(state="visible")

        assert response.status == 201
        assert canonical_id
        assert canonical_id != request_payload["id"]
        assert "status" not in request_payload
        assert "owner_id" not in request_payload
        assert response_payload["item"]["status"] == "active"
        assert response_payload["item"]["owner_id"] == "browser-project-user"
        assert response_payload["item"]["start_date"] == "2026-09-01"
        assert response_payload["item"]["due_date"] == "2026-12-31"
        assert response_payload["item"]["budget"] == 1250.5
        assert response_payload["item"]["currency"] == "EUR"
        assert failed_requests == []

        projects = project_management.projects(organization_id)
        assert [item.project_id for item in projects] == [canonical_id]
        assert projects[0].name == "Managed Browser Project"
        assert projects[0].description == "Created through the real managed browser click path"
        assert projects[0].start_date == "2026-09-01"
        assert projects[0].due_date == "2026-12-31"
        assert projects[0].budget == 1250.5
        assert projects[0].currency == "EUR"
        assert project_management.member_role(canonical_id, "browser-project-user") == "admin"
        assert decisions.decide(
            _project_access_request(organization_id, canonical_id, "edit")
        ).allowed
        assert not decisions.decide(
            _project_access_request(organization_id, canonical_id, "delete")
        ).allowed
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


@pytest.mark.integration
def test_invalid_project_schedule_is_rejected_by_shared_service(tmp_path: Path) -> None:
    organization_id = f"browser-invalid-org-{uuid4()}"
    with _managed_browser_server(
        organization_id, tmp_path / "access-control-invalid.sqlite3"
    ) as (
        url,
        project_management,
        _decisions,
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
        _open_project_editor(page, url)
        page.locator("#portfolio-project-name").fill("Impossible Schedule")
        page.locator("#portfolio-project-start-date").fill("2026-12-31")
        page.locator("#portfolio-project-due-date").fill("2026-01-01")

        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/projects")
        ) as response_info:
            page.locator("#portfolio-project-save").click()
        response = response_info.value
        payload = response.json()

        assert response.status == 400
        assert payload["error"] == "invalid_request"
        assert "cannot be before" in payload["detail"]
        page.locator("#portfolio-project-editor").wait_for(state="visible")
        assert project_management.projects(organization_id) == ()
        assert failed_requests == []
        browser.close()
