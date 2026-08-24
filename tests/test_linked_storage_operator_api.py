from __future__ import annotations

import json
from datetime import UTC, datetime

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.operator_control import ServiceRecord, ServiceState


class _Cursor:
    def __init__(self) -> None:
        self._query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        self._query = sql
        if "linked_storage_source_events_pg" in sql:
            assert parameters == ("org-1", 100)
        else:
            assert parameters == ("org-1",)

    def fetchall(self):
        if "linked_storage_source_events_pg" in self._query:
            return [
                (
                    "archive-disabled",
                    "operator-1",
                    "source_disabled",
                    datetime(2026, 8, 24, 1, 2, 3, tzinfo=UTC),
                ),
                (
                    "archive-healthy",
                    "service-healthy",
                    "source_registered",
                    "2026-08-24T00:00:00+00:00",
                ),
            ]
        return [
            ("archive-healthy", "service-healthy", "Healthy archive", True, True),
            ("archive-stale", "service-stale", "Stale archive", True, True),
            ("archive-missing", "service-missing", "Missing service archive", True, True),
            ("archive-disabled", "service-healthy", "Disabled archive", True, False),
        ]


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return _Cursor()


class _LinkedStorage:
    def connect_factory(self):
        return _Connection()


class _Operator:
    def __init__(self) -> None:
        self._services = {
            "service-healthy": _service("service-healthy", 950),
            "service-stale": _service("service-stale", 800),
        }

    def service(self, service_id: str):
        return self._services.get(service_id)


def _service(service_id: str, heartbeat: int) -> ServiceRecord:
    return ServiceRecord(
        service_id=service_id,
        organization_id="org-1",
        name=f"Storage {service_id}",
        service_type="linked-storage",
        node_name=f"node-{service_id}",
        state=ServiceState.ACTIVE.value,
        software_version="5.4.0",
        configuration_sha256="",
        certificate_serial="ABCD",
        certificate_not_after_epoch=10_000,
        enrolled_at_epoch=1,
        last_heartbeat_epoch=heartbeat,
        drain_requested_epoch=0,
        stopped_at_epoch=0,
        revoked_at_epoch=0,
    )


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        if target == "/api/v1/operator/overview" and method == "GET":
            return ApiResponse.json(
                200,
                {
                    "organization_id": "org-1",
                    "checked_at_epoch": 1000,
                    "services": [],
                    "storage": [],
                },
            )
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(LinkedStorageOperatorApiMixin, _BaseApi):
    def __init__(self) -> None:
        self._linked_storage = _LinkedStorage()
        self._operator = _Operator()


class _ForbiddenBaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(403, {"error": "forbidden"})


class _ForbiddenApi(LinkedStorageOperatorApiMixin, _ForbiddenBaseApi):
    def __init__(self) -> None:
        self._linked_storage = _LinkedStorage()
        self._operator = _Operator()


class _ManagedLinkedStorage:
    def __init__(self) -> None:
        self.state = {"archive-1": True}
        self.lifecycle_calls: list[tuple[str, str, bool, str]] = []

    def set_source_enabled(
        self,
        storage_id: str,
        organization_id: str,
        enabled: bool,
        *,
        actor_id: str,
    ) -> bool:
        self.lifecycle_calls.append((storage_id, organization_id, enabled, actor_id))
        if storage_id not in self.state or organization_id != "org-1":
            return False
        self.state[storage_id] = enabled
        return True


class _ManageApi(LinkedStorageOperatorApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True) -> None:
        self._linked_storage = _ManagedLinkedStorage()
        self.allowed = allowed
        self.operator_checks: list[tuple[str, str]] = []
        self.identity = Identity("operator-1", IdentityKind.USER, "Operator", "org-1")

    def _identity(self, headers):
        if headers.get("authorization") != "Bearer good-token":
            raise AuthenticationFailed("invalid token")
        return "good-token", self.identity

    def _allow_operator(self, _identity, _headers, action: str, resource_id: str) -> bool:
        self.operator_checks.append((action, resource_id))
        return self.allowed


def test_operator_overview_correlates_linked_archives_and_events_without_storage_paths() -> None:
    response = _Api().dispatch("GET", "/api/v1/operator/overview", {}, b"")
    assert response.status == 200
    payload = json.loads(response.body)
    archives = {item["storage_id"]: item for item in payload["linked_archives"]}

    healthy = archives["archive-healthy"]
    assert healthy["enabled"] is True
    assert healthy["service_state"] == "active"
    assert healthy["heartbeat_age_seconds"] == 50
    assert healthy["stale"] is False

    stale = archives["archive-stale"]
    assert stale["heartbeat_age_seconds"] == 200
    assert stale["stale"] is True

    missing = archives["archive-missing"]
    assert missing["service_state"] == "missing"
    assert missing["heartbeat_age_seconds"] is None
    assert missing["stale"] is True

    disabled = archives["archive-disabled"]
    assert disabled["enabled"] is False
    assert disabled["service_state"] == "active"

    assert payload["linked_archive_events"] == [
        {
            "storage_id": "archive-disabled",
            "actor_id": "operator-1",
            "event_type": "source_disabled",
            "occurred_at": "2026-08-24T01:02:03+00:00",
        },
        {
            "storage_id": "archive-healthy",
            "actor_id": "service-healthy",
            "event_type": "source_registered",
            "occurred_at": "2026-08-24T00:00:00+00:00",
        },
    ]

    serialized = response.body.decode()
    assert "root_alias" not in serialized
    assert "root_path" not in serialized
    assert "/mnt/" not in serialized


def test_operator_enrichment_does_not_change_other_routes_or_errors() -> None:
    api = _Api()
    assert api.dispatch("GET", "/api/v1/other", {}, b"").status == 404

    forbidden = _ForbiddenApi().dispatch("GET", "/api/v1/operator/overview", {}, b"")
    assert forbidden.status == 403
    assert json.loads(forbidden.body) == {"error": "forbidden"}


def test_operator_can_disable_and_explicitly_reenable_linked_archive() -> None:
    api = _ManageApi()
    headers = {"authorization": "Bearer good-token", "x-fieldora-purpose": "administration"}

    disabled = api.dispatch(
        "POST", "/api/v1/operator/linked-archives/archive-1/disable", headers, b""
    )
    assert disabled.status == 200
    assert json.loads(disabled.body) == {
        "linked_archive": {"storage_id": "archive-1", "enabled": False}
    }
    assert api._linked_storage.state["archive-1"] is False
    assert api._linked_storage.lifecycle_calls[-1] == (
        "archive-1",
        "org-1",
        False,
        "operator-1",
    )
    assert api.operator_checks[-1] == ("storage.disable", "archive-1")

    enabled = api.dispatch(
        "POST", "/api/v1/operator/linked-archives/archive-1/enable", headers, b""
    )
    assert enabled.status == 200
    assert json.loads(enabled.body) == {
        "linked_archive": {"storage_id": "archive-1", "enabled": True}
    }
    assert api._linked_storage.state["archive-1"] is True
    assert api._linked_storage.lifecycle_calls[-1] == (
        "archive-1",
        "org-1",
        True,
        "operator-1",
    )
    assert api.operator_checks[-1] == ("storage.enable", "archive-1")
    assert "root_alias" not in enabled.body.decode()
    assert "service_id" not in enabled.body.decode()


def test_linked_archive_lifecycle_is_pbac_and_organization_scoped() -> None:
    headers = {"authorization": "Bearer good-token"}
    denied_api = _ManageApi(allowed=False)
    denied = denied_api.dispatch(
        "POST", "/api/v1/operator/linked-archives/archive-1/disable", headers, b""
    )
    assert denied.status == 403
    assert denied_api._linked_storage.state["archive-1"] is True
    assert denied_api._linked_storage.lifecycle_calls == []

    api = _ManageApi()
    missing = api.dispatch(
        "POST", "/api/v1/operator/linked-archives/foreign-archive/disable", headers, b""
    )
    assert missing.status == 404
    assert api._linked_storage.state["archive-1"] is True

    unauthorized = api.dispatch(
        "POST", "/api/v1/operator/linked-archives/archive-1/disable", {}, b""
    )
    assert unauthorized.status == 401
    assert api._linked_storage.state["archive-1"] is True
