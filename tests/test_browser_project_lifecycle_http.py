from __future__ import annotations

import contextlib
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.http import handler_for
from natureai_next.server.postgres_project_management import PostgresProjectManagementService
from natureai_next.server.project_lifecycle_api import ProjectLifecycleFieldoraApi


class _Authentication:
    def __init__(self, organization_id: str) -> None:
        self.identity = Identity(
            "browser-lifecycle-user",
            IdentityKind.USER,
            "Project Lifecycle User",
            organization_id,
            attributes={"platform_admin": "true"},
        )

    def authenticate(self, token: str) -> Identity:
        assert token == "browser-lifecycle-token"
        return self.identity


class _Science:
    def records(self, _collection: str) -> tuple[dict, ...]:
        return ()

    def put(self, _collection: str, _record: dict, _expected_revision: int | None) -> int:
        raise AssertionError("managed Project lifecycle must not write Science snapshots")


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


def _access_repository(path: Path, organization_id: str) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(path)
    repository.put_identity(
        Identity(
            "browser-lifecycle-user",
            IdentityKind.USER,
            "Project Lifecycle User",
            organization_id,
            attributes={"platform_admin": "true"},
        )
    )
    repository.put_policy(
        Policy(
            policy_id="browser-lifecycle-create",
            name="Browser lifecycle create scope",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="browser-project-lifecycle-test",
            subject_id="browser-lifecycle-user",
            role_id="",
            actions=("view", "create"),
            resource_types=("project",),
            organization_id=organization_id,
            purposes=("research",),
        )
    )
    repository.put_policy(
        Policy(
            policy_id="browser-lifecycle-manage-allocation",
            name="Browser lifecycle allocation management scope",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="browser-project-child-test",
            subject_id="browser-lifecycle-user",
            role_id="",
            actions=("manage",),
            resource_types=("project",),
            organization_id=organization_id,
            purposes=("research",),
        )
    )
    repository.put_policy(
        Policy(
            policy_id="browser-lifecycle-view-allocation",
            name="Browser lifecycle allocation view scope",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="browser-project-child-test",
            subject_id="browser-lifecycle-user",
            role_id="",
            actions=("view",),
            resource_types=("allocation",),
            organization_id=organization_id,
            purposes=("research",),
        )
    )
    return repository


@contextlib.contextmanager
def _managed_server(organization_id: str, access_database: Path):
    project_management = PostgresProjectManagementService(_connect_factory())
    access_repository = _access_repository(access_database, organization_id)
    decisions = PolicyDecisionService(access_repository)
    api = ProjectLifecycleFieldoraApi(
        _Authentication(organization_id),
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
        yield f"http://127.0.0.1:{server.server_port}/", project_management
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _open_projects(page) -> None:
    page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
    page.locator("#workspace").wait_for(state="visible")
    page.locator('[data-page="research"]').click()
    page.locator("#page-research").wait_for(state="visible")
    page.locator('#page-research [data-workspace-target="projects"]').click()
    page.locator("#page-projects").wait_for(state="visible")


def _create_project(page) -> str:
    page.locator("#portfolio-new-project").click()
    page.locator("#portfolio-project-editor").wait_for(state="visible")
    page.locator("#portfolio-project-name").fill("Lifecycle Project")
    page.locator("#portfolio-project-description").fill("Initial description")
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/v1/projects")
    ) as response_info:
        page.locator("#portfolio-project-save").click()
    response = response_info.value
    assert response.status == 201
    project_id = response.json()["item"]["id"]
    page.locator(f'[data-project-tree="{project_id}"]').wait_for(state="visible")
    return project_id


@pytest.mark.integration
def test_project_edit_status_archive_and_conflict_are_revision_safe(tmp_path: Path) -> None:
    organization_id = f"browser-lifecycle-org-{uuid4()}"
    with _managed_server(
        organization_id, tmp_path / "access-control.sqlite3"
    ) as (url, project_management), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-lifecycle-token')"
        )
        page.goto(url)
        _open_projects(page)
        project_id = _create_project(page)
        created = project_management.projects(organization_id)[0]
        created_revision = created.revision

        tree_item = page.locator(f'[data-project-tree="{project_id}"]')
        tree_item.click()
        edit_button = page.locator("#portfolio-edit-project")
        page.wait_for_function(
            "document.getElementById('portfolio-edit-project').dataset.fieldoraAuthorizationHidden === 'false'"
        )
        assert edit_button.is_visible()
        edit_button.click()
        editor = page.locator("#portfolio-project-lifecycle-editor")
        editor.wait_for(state="visible")
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == (
            f"Server revision {created_revision}"
        )

        page.locator("#portfolio-project-lifecycle-name").fill("Lifecycle Project Updated")
        page.locator("#portfolio-project-lifecycle-description").fill("Browser revision-safe edit")
        with page.expect_response(
            lambda response: response.request.method == "PATCH"
            and response.url.endswith(f"/api/v1/projects/{project_id}")
        ) as update_info:
            page.locator("#portfolio-project-lifecycle-save").click()
        assert update_info.value.status == 200
        page.get_by_text("Project details saved.", exact=True).wait_for(state="visible")
        updated = project_management.projects(organization_id)[0]
        assert updated.name == "Lifecycle Project Updated"
        assert updated.revision > created_revision
        updated_revision = updated.revision
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == (
            f"Server revision {updated_revision}"
        )

        page.locator("#portfolio-project-lifecycle-status").select_option("cancelled")
        with page.expect_response(
            lambda response: response.request.method == "PATCH"
            and response.url.endswith(f"/api/v1/projects/{project_id}/status")
        ) as status_info:
            page.locator("#portfolio-project-lifecycle-apply-status").click()
        assert status_info.value.status == 200
        assert status_info.value.request.post_data_json["status"] == "cancelled"
        page.get_by_text("Project status updated.", exact=True).wait_for(state="visible")
        current = project_management.projects(organization_id)[0]
        assert current.status == "cancelled"
        assert current.revision > updated_revision
        status_revision = current.revision
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == (
            f"Server revision {status_revision}"
        )

        project_management.update_project(
            project_id,
            organization_id=organization_id,
            actor_id="concurrent-server-user",
            expected_revision=status_revision,
            description="Concurrent server edit",
        )
        concurrent = project_management.projects(organization_id)[0]
        assert concurrent.revision > status_revision
        concurrent_revision = concurrent.revision
        page.locator("#portfolio-project-lifecycle-description").fill("Stale browser overwrite")
        with page.expect_response(
            lambda response: response.request.method == "PATCH"
            and response.url.endswith(f"/api/v1/projects/{project_id}")
        ) as conflict_info:
            page.locator("#portfolio-project-lifecycle-save").click()
        assert conflict_info.value.status == 409
        page.get_by_text(
            "Project changed on the server. Latest values reloaded; review them before saving again.",
            exact=True,
        ).wait_for(state="visible")
        assert (
            page.locator("#portfolio-project-lifecycle-description").input_value()
            == "Concurrent server edit"
        )
        after_conflict = project_management.projects(organization_id)[0]
        assert after_conflict.description == "Concurrent server edit"
        assert after_conflict.revision == concurrent_revision
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == (
            f"Server revision {concurrent_revision}"
        )

        with page.expect_response(
            lambda response: response.request.method == "PATCH"
            and response.url.endswith(f"/api/v1/projects/{project_id}/archive")
        ) as archive_info:
            page.locator("#portfolio-project-lifecycle-archive").click()
        assert archive_info.value.status == 200
        archived = project_management.projects(organization_id)[0]
        assert archived.status == "archived"
        assert archived.revision > concurrent_revision
        events = [event["event_type"] for event in project_management.activity(project_id)]
        assert events == [
            "project.created",
            "project.updated",
            "project.status_changed",
            "project.updated",
            "project.archived",
        ]
        browser.close()


@pytest.mark.integration
def test_project_child_controls_persist_authoritative_hierarchy_and_allocation(tmp_path: Path) -> None:
    organization_id = f"browser-children-org-{uuid4()}"
    with _managed_server(
        organization_id, tmp_path / "access-control-children.sqlite3"
    ) as (url, project_management), sync_playwright() as playwright:
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
            "sessionStorage.setItem('fieldora-session','browser-lifecycle-token')"
        )
        page.goto(url)
        _open_projects(page)
        project_id = _create_project(page)
        page.locator(f'[data-project-tree="{project_id}"]').click()

        work_editor = page.locator("#work-save").locator("xpath=ancestor::details[1]")
        if work_editor.count():
            work_editor.locator("summary").click()
        page.locator("#work-type").select_option("phase")
        page.locator("#work-project").select_option(project_id)
        page.locator("#work-name").fill("Browser Field Phase")
        page.locator("#work-description").fill("Created through governed PM")
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/phases")
        ) as phase_info:
            page.locator("#work-save").click()
        phase_response = phase_info.value
        phase = phase_response.json()["item"]
        assert phase_response.status == 201
        assert phase["id"] != phase_response.request.post_data_json["id"]
        page.get_by_text("Browser Field Phase", exact=False).first.wait_for(state="visible")

        page.locator("#work-type").select_option("sprint")
        page.locator("#work-name").fill("Browser September Sprint")
        page.locator("#work-parent").fill("")
        page.locator("#work-sprint").fill("")
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/sprints")
        ) as sprint_info:
            page.locator("#work-save").click()
        sprint_response = sprint_info.value
        sprint = sprint_response.json()["item"]
        assert sprint_response.status == 201
        assert sprint["status"] == "planned"
        assert sprint["id"] != sprint_response.request.post_data_json["id"]

        page.locator("#work-type").select_option("task")
        page.locator("#work-name").fill("Browser Survey Task")
        page.locator("#work-parent").fill(phase["id"])
        page.locator("#work-sprint").fill(sprint["id"])
        page.locator("#work-assignee").fill("browser-lifecycle-user")
        page.locator("#work-estimate").fill("5.5")
        page.locator("#work-realized").fill("1.25")
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/tasks")
        ) as task_info:
            page.locator("#work-save").click()
        task_response = task_info.value
        task = task_response.json()["item"]
        assert task_response.status == 201
        assert task["status"] == "To Do"
        assert task["phase_id"] == phase["id"]
        assert task["sprint_id"] == sprint["id"]
        assert task["manual_estimate"] == 5.5
        assert task["realized"] == 1.25
        assert task["id"] != task_response.request.post_data_json["id"]
        page.get_by_text("Browser Survey Task", exact=False).first.wait_for(state="visible")

        page.locator('#page-projects [data-workspace-target="capacity"]').click()
        page.locator("#page-capacity").wait_for(state="visible")
        page.locator("#capacity-type").select_option("allocation")
        page.locator("#capacity-user").fill("browser-lifecycle-user")
        page.locator("#capacity-project").select_option(project_id)
        page.locator("#capacity-start").fill("2026-09-01T09:00")
        page.locator("#capacity-end").fill("2026-09-30T17:00")
        page.locator("#capacity-hours").fill("24")
        page.locator("#capacity-description").fill("Field lead")
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/api/v1/allocations")
        ) as allocation_info:
            page.locator("#capacity-save").click()
        allocation_response = allocation_info.value
        allocation = allocation_response.json()["item"]
        assert allocation_response.status == 201
        assert allocation["id"] != allocation_response.request.post_data_json["id"]
        assert allocation["hours_per_week"] == 24
        assert allocation["role"] == "Field lead"
        page.locator("#allocation-list").get_by_text(
            "browser-lifecycle-user", exact=True
        ).wait_for(state="visible")

        phases = project_management.phases(organization_id)
        sprints = project_management.sprints(organization_id)
        tasks = project_management.tasks(organization_id)
        allocations = project_management.allocations(organization_id)
        assert [item["id"] for item in phases] == [phase["id"]]
        assert [item["id"] for item in sprints] == [sprint["id"]]
        assert [item["id"] for item in tasks] == [task["id"]]
        assert [item["id"] for item in allocations] == [allocation["id"]]
        assert [event["event_type"] for event in project_management.activity(project_id)] == [
            "project.created",
            "phase.created",
            "sprint.created",
            "task.created",
            "allocation.updated",
        ]
        assert failed_requests == []
        browser.close()


@pytest.mark.integration
def test_project_lifecycle_controls_remain_absent_without_selected_edit_scope(tmp_path: Path) -> None:
    organization_id = f"browser-lifecycle-denied-{uuid4()}"
    with _managed_server(
        organization_id, tmp_path / "access-control.sqlite3"
    ) as (url, project_management), sync_playwright() as playwright:
        project = project_management.create_project(
            "Read Only Project",
            organization_id=organization_id,
            owner_id="different-owner",
            actor_id="different-owner",
        )
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-lifecycle-token')"
        )
        page.goto(url)
        _open_projects(page)
        page.locator(f'[data-project-tree="{project}"]').click()
        page.wait_for_timeout(100)
        assert (
            page.locator("#portfolio-edit-project").get_attribute(
                "data-fieldora-authorization-hidden"
            )
            == "true"
        )
        assert not page.locator("#portfolio-edit-project").is_visible()
        browser.close()
