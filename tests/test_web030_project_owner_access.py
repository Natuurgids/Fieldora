from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import SimpleNamespace

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.domain.access_control import (
    AccessRequest,
    IdentityKind,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi


@dataclass(frozen=True)
class _Project:
    project_id: str
    organization_id: str
    name: str
    owner_id: str
    status: str = "active"
    start_date: str = ""
    due_date: str = ""
    budget: float = 0.0
    currency: str = "EUR"
    description: str = ""
    revision: int = 100


class _ProjectService:
    def __init__(self) -> None:
        self.created: list[_Project] = []

    def create_project(
        self,
        name: str,
        *,
        organization_id: str,
        owner_id: str,
        actor_id: str,
        start_date: str = "",
        due_date: str = "",
        description: str = "",
        budget: float = 0,
        currency: str = "EUR",
        template_id: str | None = None,
    ) -> str:
        assert actor_id == owner_id
        assert template_id is None
        project_id = "project-created-by-managed-service"
        self.created.append(
            _Project(
                project_id=project_id,
                organization_id=organization_id,
                name=name,
                owner_id=owner_id,
                start_date=start_date,
                due_date=due_date,
                description=description,
                budget=float(budget),
                currency=currency,
            )
        )
        return project_id

    def projects(self, organization_id: str) -> tuple[_Project, ...]:
        return tuple(
            project
            for project in self.created
            if project.organization_id == organization_id
        )

    def update_project(
        self,
        project_id: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
        name: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        due_date: str | None = None,
        budget: float | None = None,
        currency: str | None = None,
    ) -> int:
        for index, project in enumerate(self.created):
            if project.project_id != project_id or project.organization_id != organization_id:
                continue
            assert actor_id == project.owner_id
            if project.revision != expected_revision:
                raise ValueError("project revision conflict")
            revision = project.revision + 1
            self.created[index] = replace(
                project,
                name=project.name if name is None else name,
                description=project.description if description is None else description,
                start_date=project.start_date if start_date is None else start_date,
                due_date=project.due_date if due_date is None else due_date,
                budget=project.budget if budget is None else float(budget),
                currency=project.currency if currency is None else currency,
                revision=revision,
            )
            return revision
        raise KeyError(project_id)


class _ManagedApi(BrowserFunctionalityFieldoraApi):
    def __init__(self, service, repository, identity) -> None:
        self._project_management = service
        self._access_repository = repository
        self._decisions = PolicyDecisionService(repository)
        self._test_identity = identity

    def _identity(self, _headers):
        return "token", SimpleNamespace(
            identity_id=self._test_identity.identity_id,
            organization_id=self._test_identity.organization_id,
        )


def _request(identity_id: str, action: str, resource_type: str, project_id: str):
    return AccessRequest(
        identity_id,
        action,
        resource_type,
        project_id if resource_type == "project" else "child-id",
        "organization-1",
        project_id,
        "research",
    )


def test_creator_immediately_gets_only_project_scoped_workspace_authority(tmp_path) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    administration.create_organization("organization-1", "Organization One")
    creator = administration.create_identity(
        "Creator", "organization-1", IdentityKind.USER
    )
    outsider = administration.create_identity(
        "Outsider", "organization-1", IdentityKind.USER
    )
    administration.create_policy(
        name="May create projects",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=creator.identity_id,
        actions=("create",),
        resource_types=("project",),
        organization_id="organization-1",
        purposes=("research",),
    )

    service = _ProjectService()
    api = _ManagedApi(service, repository, creator)
    created = api._create_project(
        {"x-fieldora-purpose": "research"},
        b'{"name":"Immediate access project"}',
    )

    assert created.status == 201
    payload = json.loads(created.body)
    project_id = payload["item"]["id"]
    revision = payload["item"]["revision"]
    assert service.created[0].owner_id == creator.identity_id

    visible = api._managed_projects({"x-fieldora-purpose": "research"})
    assert visible.status == 200
    assert [item["id"] for item in json.loads(visible.body)["items"]] == [project_id]

    edited = api._update_project(
        project_id,
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {"expected_revision": revision, "name": "Immediately editable project"}
        ).encode("utf-8"),
    )
    assert edited.status == 200
    assert json.loads(edited.body)["item"]["name"] == "Immediately editable project"

    decisions = PolicyDecisionService(repository)
    assert decisions.decide(_request(creator.identity_id, "view", "project", project_id)).allowed
    assert decisions.decide(_request(creator.identity_id, "edit", "project", project_id)).allowed
    assert decisions.decide(_request(creator.identity_id, "edit", "phase", project_id)).allowed
    assert decisions.decide(_request(creator.identity_id, "edit", "task", project_id)).allowed

    assert not decisions.decide(
        _request(outsider.identity_id, "view", "project", project_id)
    ).allowed
    assert not decisions.decide(
        _request(creator.identity_id, "edit", "project", "some-other-project")
    ).allowed
    assert not decisions.decide(
        AccessRequest(
            creator.identity_id,
            "view_audit",
            "security_audit",
            "",
            "organization-1",
            project_id,
            "administration",
        )
    ).allowed


def test_explicit_deny_still_overrides_creator_owner_grant(tmp_path) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    administration.create_organization("organization-1", "Organization One")
    creator = administration.create_identity(
        "Creator", "organization-1", IdentityKind.USER
    )
    administration.create_policy(
        name="May create projects",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        subject_id=creator.identity_id,
        actions=("create",),
        resource_types=("project",),
        organization_id="organization-1",
        purposes=("research",),
    )

    service = _ProjectService()
    api = _ManagedApi(service, repository, creator)
    created = api._create_project(
        {"x-fieldora-purpose": "research"},
        b'{"name":"Deny remains authoritative"}',
    )
    assert created.status == 201
    project_id = json.loads(created.body)["item"]["id"]

    administration.create_policy(
        name="Project-specific edit deny",
        effect=PolicyEffect.DENY,
        source=PolicySource.DIRECT,
        subject_id=creator.identity_id,
        actions=("edit",),
        resource_types=("project",),
        resource_id=project_id,
        organization_id="organization-1",
        project_id=project_id,
        purposes=("research",),
    )

    decision = PolicyDecisionService(repository).decide(
        _request(creator.identity_id, "edit", "project", project_id)
    )
    assert not decision.allowed
    assert decision.reason.startswith("explicit deny:")
