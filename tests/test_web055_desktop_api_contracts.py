from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from natureai_next.server.project_idempotency import (
    ProjectIdempotencyApiMixin,
    ProjectMutationConflict,
)


class _DecisionService:
    def decide(self, _request):
        return SimpleNamespace(allowed=True)


class _ProjectContractService:
    """Small shared-service fixture used by direct/desktop and HTTP adapters."""

    def __init__(self) -> None:
        self.requests: dict[str, tuple[object, ...]] = {}

    def create_project_idempotent(self, project_id: str, name: str, **kwargs):
        request = (
            name,
            kwargs["organization_id"],
            kwargs["owner_id"],
            kwargs["start_date"],
            kwargs["due_date"],
            kwargs["description"],
            float(kwargs["budget"]),
            kwargs["currency"],
            kwargs["template_id"],
        )
        previous = self.requests.get(project_id)
        if previous is not None and previous != request:
            raise ProjectMutationConflict(
                "project mutation identity already belongs to another payload"
            )
        replayed = previous is not None
        self.requests[project_id] = request
        return project_id, replayed


class _ProjectApi(ProjectIdempotencyApiMixin):
    def __init__(self, service: _ProjectContractService) -> None:
        self._project_management = service
        self._decisions = _DecisionService()
        self.owner_grants: list[str] = []
        self.project = SimpleNamespace(revision=1)

    def _identity(self, _headers):
        return "token", SimpleNamespace(identity_id="user-1", organization_id="org-1")

    def _grant_project_owner(
        self, _identity_id: str, _organization_id: str, project_id: str, _name: str
    ) -> None:
        self.owner_grants.append(project_id)

    def _project_for_organization(self, _organization_id: str, _project_id: str):
        return self.project

    @staticmethod
    def _project_item(item):
        return {"revision": item.revision}


def _direct_create(service: _ProjectContractService, project_id: str, name: str):
    return service.create_project_idempotent(
        project_id,
        name,
        organization_id="org-1",
        owner_id="user-1",
        actor_id="user-1",
        start_date="2026-09-01",
        due_date="2026-12-31",
        description="Seasonal field survey",
        budget=1250.5,
        currency="EUR",
        template_id=None,
    )


def _api_create(api: _ProjectApi, project_id: str, name: str):
    body = json.dumps(
        {
            "id": project_id,
            "name": name,
            "start_date": "2026-09-01",
            "due_date": "2026-12-31",
            "description": "Seasonal field survey",
            "budget": 1250.5,
            "currency": "EUR",
        }
    ).encode()
    response = api.dispatch("POST", "/api/v1/projects", {}, body)
    return response, json.loads(response.body)


def test_web055_desktop_and_api_project_create_have_equivalent_domain_outcomes() -> None:
    project_id = "web055-project"
    direct_service = _ProjectContractService()
    api_service = _ProjectContractService()

    direct_id, direct_replayed = _direct_create(
        direct_service, project_id, "Wetland Survey"
    )
    response, payload = _api_create(_ProjectApi(api_service), project_id, "Wetland Survey")

    assert (direct_id, direct_replayed) == (project_id, False)
    assert response.status == 201
    assert payload["replayed"] is False
    assert direct_service.requests == api_service.requests


def test_web055_desktop_and_api_replay_and_conflict_contracts_are_equivalent() -> None:
    project_id = "web055-replay"
    direct_service = _ProjectContractService()
    api_service = _ProjectContractService()
    api = _ProjectApi(api_service)

    assert _direct_create(direct_service, project_id, "Wetland Survey")[1] is False
    assert _direct_create(direct_service, project_id, "Wetland Survey")[1] is True
    first, _ = _api_create(api, project_id, "Wetland Survey")
    replay, replay_payload = _api_create(api, project_id, "Wetland Survey")
    assert first.status == 201
    assert replay.status == 200
    assert replay_payload["replayed"] is True

    with pytest.raises(ProjectMutationConflict):
        _direct_create(direct_service, project_id, "Changed")
    conflict, conflict_payload = _api_create(api, project_id, "Changed")
    assert conflict.status == 409
    assert conflict_payload == {"error": "idempotency_conflict"}
    assert direct_service.requests == api_service.requests


def test_web055_real_desktop_and_server_wiring_stays_on_project_service_boundaries() -> None:
    desktop = Path("src/natureai_next/ui/qt/project_management.py").read_text(
        encoding="utf-8"
    )
    server = Path("src/natureai_next/server/offline_first_api.py").read_text(
        encoding="utf-8"
    )

    assert "self._projects.create_project(" in desktop
    assert "self._projects.update_project(" in desktop
    assert "wrap_project_management(project_management)" in server
    assert "ProjectIdempotencyApiMixin" in server
