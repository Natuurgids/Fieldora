from __future__ import annotations

import contextlib
import hashlib
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import Page, sync_playwright

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.application.project_management import ProjectManagementService
from natureai_next.domain.access_control import (
    AccessRequest,
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.http import handler_for
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.object_storage import FileObjectStore
from natureai_next.server.project_lifecycle_api import ProjectLifecycleFieldoraApi
from natureai_next.server.project_runtime_web import ProjectRuntimeWebApiMixin


class _Authentication:
    def __init__(self) -> None:
        self.identity = Identity("creator-1", IdentityKind.USER, "Creator", "local")

    def authenticate(self, token: str) -> Identity:
        assert token == "browser-token"
        return self.identity


class _Science:
    def records(self, _collection: str) -> tuple[dict, ...]:
        return ()

    def put(self, _collection: str, _record: dict, _expected_revision: int | None) -> int:
        return 1


class _ManagedSqliteProjects:
    """Organization-shaped adapter over the real shared Project domain service."""

    def __init__(self, database_path: Path) -> None:
        self.service = ProjectManagementService(database_path)
        self.revisions: dict[str, int] = {}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.service.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def projects(self, organization_id: str):
        assert organization_id == "local"
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM pm_projects ORDER BY updated_at_us DESC").fetchall()
        return tuple(
            SimpleNamespace(
                project_id=str(row["project_id"]),
                organization_id=organization_id,
                name=str(row["name"]),
                description=str(row["description"]),
                status=str(row["status"]),
                owner_id=str(row["owner_id"]),
                start_date=str(row["start_date"]),
                due_date=str(row["due_date"]),
                budget=float(row["budget"]),
                currency=str(row["currency"]),
                revision=self.revisions.get(str(row["project_id"]), 1),
            )
            for row in rows
        )

    def create_project(self, name: str, *, organization_id: str, owner_id: str, actor_id: str, **kwargs):
        assert organization_id == "local"
        project_id = self.service.create_project(name, owner_id=owner_id, actor_id=actor_id, **kwargs)
        self.revisions[project_id] = 1
        return project_id

    def update_project(
        self,
        project_id: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
        **changes,
    ) -> int:
        assert organization_id == "local"
        self.service.require(project_id, actor_id, "edit")
        current = self.revisions.get(project_id, 1)
        if current != expected_revision:
            raise ValueError("revision conflict")
        allowed = {"name", "description", "start_date", "due_date", "budget", "currency"}
        values = {key: value for key, value in changes.items() if key in allowed and value is not None}
        if values:
            assignments = ",".join(f"{key}=?" for key in values)
            with self._connect() as connection:
                connection.execute(
                    f"UPDATE pm_projects SET {assignments},updated_at_us=updated_at_us+1 WHERE project_id=?",
                    (*values.values(), project_id),
                )
        self.revisions[project_id] = current + 1
        return current + 1

    def archive_project(self, project_id: str, *, organization_id: str, actor_id: str, expected_revision: int):
        return self.update_project(
            project_id,
            organization_id=organization_id,
            actor_id=actor_id,
            expected_revision=expected_revision,
        )

    def set_project_status(self, project_id: str, status: str, *, organization_id: str, actor_id: str, expected_revision: int):
        assert organization_id == "local"
        self.service.require(project_id, actor_id, "edit")
        current = self.revisions.get(project_id, 1)
        if current != expected_revision:
            raise ValueError("revision conflict")
        with self._connect() as connection:
            connection.execute("UPDATE pm_projects SET status=?,updated_at_us=updated_at_us+1 WHERE project_id=?", (status, project_id))
        self.revisions[project_id] = current + 1
        return current + 1

    def tasks(self, organization_id: str):
        items: list[dict[str, object]] = []
        for project in self.projects(organization_id):
            for task in self.service.tasks(project.project_id):
                items.append(
                    {
                        "id": task.task_id,
                        "project_id": task.project_id,
                        "title": task.title,
                        "owner_id": task.owner_id,
                        "parent_task_id": task.parent_task_id,
                    }
                )
        return tuple(items)

    def create_task(self, project_id: str, name: str, *, organization_id: str, actor_id: str, **kwargs):
        assert organization_id == "local"
        return self.service.create_task(project_id, name, actor_id=actor_id, **kwargs)

    def phases(self, _organization_id: str):
        return ()

    def sprints(self, _organization_id: str):
        return ()

    def allocations(self, _organization_id: str):
        return ()


class _RuntimeApi(ProjectRuntimeWebApiMixin, ProjectLifecycleFieldoraApi):
    pass


def _access_repository(tmp_path: Path) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    repository.put_organization(Organization("local", "Local"))
    repository.put_identity(Identity("creator-1", IdentityKind.USER, "Creator", "local"))
    for policy in (
        Policy(
            "project-create-view",
            "Create and view Projects",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "creator-1",
            "",
            ("create", "view"),
            ("project",),
            organization_id="local",
            purposes=("research",),
        ),
        Policy(
            "library-view-upload",
            "Use governed Library",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "creator-1",
            "",
            ("view", "upload"),
            ("asset",),
            organization_id="local",
            purposes=("research",),
        ),
    ):
        repository.put_policy(policy)
    return repository


@contextlib.contextmanager
def _live_server(tmp_path: Path):
    access = _access_repository(tmp_path)
    decisions = PolicyDecisionService(access)
    projects = _ManagedSqliteProjects(tmp_path / "projects.sqlite3")
    media = GovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "objects",
        object_store=FileObjectStore(tmp_path / "objects"),
    )
    _RuntimeApi.configure_project_management(lambda: projects)
    api = _RuntimeApi(
        _Authentication(),
        decisions,
        _Science(),
        Path("src/natureai_next/resources/server_web"),
        media,
        audit_repository=access,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(api))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", projects, media, access, decisions
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _RuntimeApi.configure_project_management(None)


def _upload_preexisting(page: Page) -> str:
    payload = b"pre-existing governed evidence"
    digest = hashlib.sha256(payload).hexdigest()
    page.locator('[data-page="library"]').click()
    page.locator("#upload-file").set_input_files(
        {"name": "existing.jpg", "mimeType": "image/jpeg", "buffer": payload}
    )
    page.locator("#upload-start").click()
    page.wait_for_function(
        "document.querySelector('#upload-status').textContent.includes('1 file verified')"
    )
    return digest


def test_web058_project_runtime_inside_docker(tmp_path: Path) -> None:
    with _live_server(tmp_path) as (url, projects, media, access, decisions), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script("sessionStorage.setItem('fieldora-session','browser-token')")
        page.goto(url)
        page.locator("#workspace").wait_for(state="visible")

        evidence_sha = _upload_preexisting(page)
        evidence = next(record for record in media.records("local") if record.sha256 == evidence_sha)
        assert evidence.project_id == ""
        assert media.associations.links(evidence.media_id, "local") == ()

        page.locator('[data-page="projects"]').click()
        page.locator("#portfolio-new-project").click()
        page.locator("#portfolio-project-name").fill("WEB-058 Runtime Project")
        page.locator("#portfolio-project-description").fill("Created in the real browser runtime")
        page.locator("#portfolio-project-save").click()
        page.locator("#portfolio-project-editor").wait_for(state="hidden")
        project = next(item for item in projects.projects("local") if item.name == "WEB-058 Runtime Project")

        edit_decision = decisions.decide(
            AccessRequest("creator-1", "edit", "project", project.project_id, "local", project.project_id, "research")
        )
        link_decision = decisions.decide(
            AccessRequest("creator-1", "link", "asset", evidence.media_id, "local", project.project_id, "research")
        )
        assert edit_decision.allowed and link_decision.allowed
        owner_policies = [policy for policy in access.policies() if policy.source is PolicySource.OBJECT_GRANT and policy.source_id == project.project_id]
        assert len(owner_policies) == 1

        page.evaluate(
            "id=>{selectedProject=id;return loadPortfolio()}",
            project.project_id,
        )
        page.locator("#portfolio-edit-project").click()
        page.locator("#portfolio-project-lifecycle-name").fill("WEB-058 Runtime Project Edited")
        page.locator("#portfolio-project-lifecycle-description").fill("Persisted browser edit")
        page.locator("#portfolio-project-lifecycle-save").click()
        page.wait_for_function(
            "document.querySelector('#portfolio-project-lifecycle-message').textContent.includes('saved')"
        )

        page.reload()
        page.locator("#workspace").wait_for(state="visible")
        page.locator('[data-page="projects"]').click()
        page.evaluate("id=>{selectedProject=id;return loadPortfolio()}", project.project_id)
        page.locator("#portfolio-edit-project").click()
        assert page.locator("#portfolio-project-lifecycle-name").input_value() == "WEB-058 Runtime Project Edited"
        assert page.locator("#portfolio-project-lifecycle-description").input_value() == "Persisted browser edit"

        page.locator("#portfolio-project-work").click()
        page.locator("#portfolio-project-task-title").fill("Collect follow-up sample")
        page.locator("#portfolio-project-task-add").click()
        page.wait_for_function(
            "document.querySelector('#portfolio-project-runtime-message').textContent.includes('Task added')"
        )
        tasks = projects.service.tasks(project.project_id)
        assert [task.title for task in tasks] == ["Collect follow-up sample"]

        page.locator("#portfolio-project-evidence").select_option(evidence.media_id)
        page.locator("#portfolio-project-evidence-link").click()
        page.wait_for_function(
            "document.querySelector('#portfolio-project-runtime-message').textContent.includes('without changing its identity')"
        )
        links = media.associations.links(evidence.media_id, "local")
        assert [(link.association_type, link.target_id) for link in links] == [("project", project.project_id)]
        same = media.record(evidence.media_id)
        assert same is not None
        assert same.media_id == evidence.media_id
        assert same.sha256 == evidence.sha256
        assert same.project_id == ""
        assert len(media.instances(evidence.media_id, "local")) == 1
        browser.close()
