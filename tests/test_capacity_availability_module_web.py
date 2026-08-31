from __future__ import annotations

import json
from types import SimpleNamespace

from natureai_next.server.api import ApiResponse
from natureai_next.server.capacity_availability_module_web import (
    CapacityAvailabilityModuleWebApiMixin,
)
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.web_module_contracts import foundation_registry


class _Decisions:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def decide(self, _request):
        return SimpleNamespace(allowed=self.allowed)


class _Service:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def workload(self, project_id: str):
        assert project_id == "p1"
        return (
            {
                "user_id": "u1",
                "role": "manager",
                "scheduled_hours": 40.0,
                "absence_hours": 8.0,
                "organisational_hours": 2.0,
                "allocated_hours": 20.0,
                "remaining_hours": 10.0,
            },
        )

    def schedule_templates(self):
        return ({"template_id": "standard-40h", "name": "40 hours"},)

    def project_members(self, project_id: str):
        assert project_id == "p1"
        return ({"user_id": "u1"},)

    def assign_work_schedule(self, user_id, template_id, effective_from, *, actor_id):
        self.calls.append(("schedule", user_id, template_id, effective_from, actor_id))
        return "schedule-1"

    def add_absence(self, user_id, start_at, end_at, absence_type, *, actor_id):
        self.calls.append(("absence", user_id, start_at, end_at, absence_type, actor_id))
        return "absence-1"

    def add_organisational_obligation(
        self, user_id, start_at, end_at, obligation_type, title, *, actor_id
    ):
        self.calls.append(
            ("obligation", user_id, start_at, end_at, obligation_type, title, actor_id)
        )
        return "obligation-1"


class _Base:
    def dispatch(self, _method, _target, _headers, _body):
        return ApiResponse.json(404, {"error": "base"})


class _Harness(CapacityAvailabilityModuleWebApiMixin, _Base):
    def __init__(self, *, allowed: bool = True) -> None:
        self._project_management = _Service()
        self._decisions = _Decisions(allowed)

    def _identity(self, _headers):
        return "token", SimpleNamespace(
            identity_id="actor-1", organization_id="org-1"
        )

    def _project_for_organization(self, organization_id: str, project_id: str):
        if organization_id == "org-1" and project_id == "p1":
            return {"id": "p1"}
        return None


def _json(response: ApiResponse) -> dict:
    return json.loads(response.body)


def test_capacity_contract_owns_desktop_availability_actions() -> None:
    registry = foundation_registry()
    for action in (
        "capacity.availability.view",
        "capacity.schedule.assign",
        "capacity.absence.register",
        "capacity.obligation.create",
    ):
        owner = registry.action_owner(action)
        assert owner is not None
        assert owner.module_id == "capacity"


def test_browser_adapter_is_lifecycle_owned_and_hides_private_hr_detail() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = CapacityAvailabilityModuleWebApiMixin._patch_browser("/app.js", original)
    again = CapacityAvailabilityModuleWebApiMixin._patch_browser("/app.js", patched)
    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-CAPACITY-AVAILABILITY-MODULE" in script
    assert "window.FieldoraCapacityAvailability=Object.freeze" in script
    assert "fieldora:capacity-project-changed" in script
    assert "/api/v1/capacity/availability?project_id=" in script
    assert 'data-fieldora-action="capacity.schedule.assign"' in script
    assert 'data-fieldora-action="capacity.absence.register"' in script
    assert 'data-fieldora-action="capacity.obligation.create"' in script
    assert "private HR details stay server-side" in script
    assert "loadCapacity=" not in script
    assert "showPage=" not in script


def test_availability_read_returns_aggregate_workload_and_templates() -> None:
    api = _Harness()
    response = api.dispatch(
        "GET", "/api/v1/capacity/availability?project_id=p1", {}, b""
    )
    payload = _json(response)
    assert response.status == 200
    assert payload["count"] == 1
    assert payload["items"][0]["remaining_hours"] == 10.0
    assert payload["schedule_templates"][0]["template_id"] == "standard-40h"
    assert "privacy_level" not in json.dumps(payload)


def test_capacity_writes_require_project_edit_and_project_member() -> None:
    denied = _Harness(allowed=False)
    response = denied.dispatch(
        "POST",
        "/api/v1/capacity/absences",
        {},
        json.dumps(
            {
                "project_id": "p1",
                "user_id": "u1",
                "start_at": "2026-09-01T09:00",
                "end_at": "2026-09-01T17:00",
                "absence_type": "pto",
            }
        ).encode(),
    )
    assert response.status == 403

    api = _Harness()
    response = api.dispatch(
        "POST",
        "/api/v1/capacity/schedules",
        {},
        json.dumps(
            {
                "project_id": "p1",
                "user_id": "outsider",
                "template_id": "standard-40h",
                "effective_from": "2026-09-01",
            }
        ).encode(),
    )
    assert response.status == 400
    assert _json(response)["error"] == "invalid_project_member"


def test_schedule_absence_and_obligation_use_shared_service() -> None:
    api = _Harness()
    cases = (
        (
            "/api/v1/capacity/schedules",
            {
                "project_id": "p1",
                "user_id": "u1",
                "template_id": "standard-40h",
                "effective_from": "2026-09-01",
            },
            "schedule",
        ),
        (
            "/api/v1/capacity/absences",
            {
                "project_id": "p1",
                "user_id": "u1",
                "start_at": "2026-09-01T09:00",
                "end_at": "2026-09-01T17:00",
                "absence_type": "annual_leave",
            },
            "absence",
        ),
        (
            "/api/v1/capacity/obligations",
            {
                "project_id": "p1",
                "user_id": "u1",
                "start_at": "2026-09-02T10:00",
                "end_at": "2026-09-02T12:00",
                "title": "Team seminar",
            },
            "obligation",
        ),
    )
    for path, body, expected_kind in cases:
        response = api.dispatch("POST", path, {}, json.dumps(body).encode())
        assert response.status == 201
        assert _json(response)["kind"] == expected_kind
    assert [call[0] for call in api._project_management.calls] == [
        "schedule",
        "absence",
        "obligation",
    ]


def test_capacity_availability_mixin_is_composed_inside_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert CapacityAvailabilityModuleWebApiMixin in mro[2:]
