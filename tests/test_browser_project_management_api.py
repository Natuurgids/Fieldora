from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import SimpleNamespace

from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi


@dataclass(frozen=True)
class _Project:
    project_id: str
    organization_id: str
    name: str
    status: str = "active"
    owner_id: str = ""
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
        assert actor_id == "user-1"
        assert template_id is None
        project_id = "server-generated-project-id"
        self.created.append(
            _Project(
                project_id,
                organization_id,
                name,
                owner_id=owner_id,
                start_date=start_date,
                due_date=due_date,
                budget=float(budget),
                currency=currency,
                description=description,
            )
        )
        return project_id

    def projects(self, organization_id: str) -> tuple[_Project, ...]:
        return tuple(
            item for item in self.created if item.organization_id == organization_id
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
        assert actor_id == "user-1"
        for index, project in enumerate(self.created):
            if project.project_id != project_id or project.organization_id != organization_id:
                continue
            if expected_revision != project.revision:
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

    def archive_project(
        self,
        project_id: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> int:
        assert actor_id == "user-1"
        for index, project in enumerate(self.created):
            if project.project_id != project_id or project.organization_id != organization_id:
                continue
            if expected_revision != project.revision:
                raise ValueError("project revision conflict")
            revision = project.revision + 1
            self.created[index] = replace(project, status="archived", revision=revision)
            return revision
        raise KeyError(project_id)


class _Decisions:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed)


class _ManagedApi(BrowserFunctionalityFieldoraApi):
    def __init__(self, service: _ProjectService, *, allowed: bool = True) -> None:
        self._project_management = service
        self._decisions = _Decisions(allowed)
        self._access_repository = None

    @staticmethod
    def _identity(_headers):
        return "token", SimpleNamespace(
            identity_id="user-1",
            organization_id="organization-1",
        )


def _create(api: _ManagedApi) -> dict:
    response = api._create_project(
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "id": "browser-generated-id-must-not-win",
                "name": "Browser Project",
                "description": "Created from managed web",
                "owner_id": "user-1",
                "start_date": "2026-09-01",
                "due_date": "2026-10-01",
                "budget": 100,
                "currency": "EUR",
            }
        ).encode("utf-8"),
    )
    assert response.status == 201
    return json.loads(response.body)


def test_managed_project_create_ignores_browser_supplied_identity() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)
    payload = _create(api)

    assert payload["item"]["id"] == "server-generated-project-id"
    assert payload["item"]["id"] != "browser-generated-id-must-not-win"
    assert payload["item"]["name"] == "Browser Project"
    assert payload["item"]["revision"] == 100
    assert service.created[0].organization_id == "organization-1"
    request = api._decisions.requests[0]
    assert request.action == "create"
    assert request.resource_type == "project"
    assert request.organization_id == "organization-1"


def test_managed_project_create_uses_creator_owner_and_service_status() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)

    response = api._create_project(
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "name": "Creator-owned Project",
                "owner_id": "other-user-must-not-win",
                "status": "archived",
            }
        ).encode("utf-8"),
    )

    assert response.status == 201
    payload = json.loads(response.body)
    assert service.created[0].owner_id == "user-1"
    assert service.created[0].status == "active"
    assert payload["item"]["owner_id"] == "user-1"
    assert payload["item"]["status"] == "active"


def test_managed_project_create_denial_persists_nothing() -> None:
    service = _ProjectService()
    api = _ManagedApi(service, allowed=False)

    response = api._create_project(
        {"x-fieldora-purpose": "research"},
        b'{"name":"Denied Project"}',
    )

    assert response.status == 403
    assert service.created == []


def test_managed_project_edit_requires_edit_and_returns_new_revision() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)
    created = _create(api)

    response = api._update_project(
        "server-generated-project-id",
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "expected_revision": created["item"]["revision"],
                "name": "Edited Browser Project",
                "description": "Edited through the managed API",
                "due_date": "2026-11-30",
                "budget": 300.25,
                "currency": "USD",
            }
        ).encode("utf-8"),
    )

    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["item"]["name"] == "Edited Browser Project"
    assert payload["item"]["description"] == "Edited through the managed API"
    assert payload["item"]["revision"] == 101
    assert service.created[0].revision == 101
    edit_request = api._decisions.requests[-1]
    assert edit_request.action == "edit"
    assert edit_request.resource_type == "project"
    assert edit_request.resource_id == "server-generated-project-id"
    assert edit_request.project_id == "server-generated-project-id"


def test_managed_project_stale_edit_returns_conflict_without_overwrite() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)
    created = _create(api)
    current_revision = created["item"]["revision"]
    service.update_project(
        "server-generated-project-id",
        organization_id="organization-1",
        actor_id="user-1",
        expected_revision=current_revision,
        name="Concurrent Winner",
    )

    response = api._update_project(
        "server-generated-project-id",
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "expected_revision": current_revision,
                "name": "Stale Browser Edit",
            }
        ).encode("utf-8"),
    )

    assert response.status == 409
    payload = json.loads(response.body)
    assert payload["error"] == "revision_conflict"
    assert payload["current"]["name"] == "Concurrent Winner"
    assert payload["current"]["revision"] == 101
    assert service.created[0].name == "Concurrent Winner"


def test_managed_project_archive_is_non_destructive_and_revision_guarded() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)
    created = _create(api)

    response = api._archive_project(
        "server-generated-project-id",
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {"expected_revision": created["item"]["revision"]}
        ).encode("utf-8"),
    )

    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["item"]["id"] == "server-generated-project-id"
    assert payload["item"]["status"] == "archived"
    assert payload["item"]["revision"] == 101
    assert len(service.created) == 1
    archive_request = api._decisions.requests[-1]
    assert archive_request.action == "edit"
    assert archive_request.resource_id == "server-generated-project-id"


def test_managed_project_edit_denial_persists_nothing() -> None:
    service = _ProjectService()
    create_api = _ManagedApi(service)
    created = _create(create_api)
    api = _ManagedApi(service, allowed=False)

    response = api._update_project(
        "server-generated-project-id",
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "expected_revision": created["item"]["revision"],
                "name": "Denied Edit",
            }
        ).encode("utf-8"),
    )

    assert response.status == 403
    assert service.created[0].name == "Browser Project"
    assert service.created[0].revision == 100
