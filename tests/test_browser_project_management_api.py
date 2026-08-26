from __future__ import annotations

import json
from dataclasses import dataclass
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


def test_managed_project_create_ignores_browser_supplied_identity() -> None:
    service = _ProjectService()
    api = _ManagedApi(service)
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
    payload = json.loads(response.body)
    assert payload["item"]["id"] == "server-generated-project-id"
    assert payload["item"]["id"] != "browser-generated-id-must-not-win"
    assert payload["item"]["name"] == "Browser Project"
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
