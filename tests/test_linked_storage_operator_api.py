from __future__ import annotations

import json

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.operator_control import ServiceRecord, ServiceState


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _sql: str, parameters: tuple[str]) -> None:
        assert parameters == ("org-1",)

    def fetchall(self):
        return [
            ("archive-healthy", "service-healthy", "Healthy archive", True),
            ("archive-stale", "service-stale", "Stale archive", True),
            ("archive-missing", "service-missing", "Missing service archive", True),
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


class _ManageCursor:
    def __init__(self, state: dict[str, bool]) -> None:
        self._state = state
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        assert "UPDATE linked_storage_sources_pg SET enabled=%s" in sql
        enabled, storage_id, organization_id = parameters
        if storage_id in self._state and organization_id == "org-1":
            self._state[str(storage_id)] = bool(enabled)
            self.rowcount = 1
        else:
            self.rowcount = 0


class _ManageConnection:
    def __init__(self, state: dict[str, bool]) -> None:
        self._state = state

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return _ManageCursor(self._state)


class _ManagedLinkedStorage:
    def __init__(self) -> None:
        self.state = {"archive-1": True}

    def connect_factory(self):
        return _ManageConnection(self.state)


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


def test_operator_overview_correlates_linked_archives_without_storage_paths() -> None:
    response = _Api().dispatch("GET", "/api/v1/operator/overview", {}, b"")
    assert response.status == 200
    payload = json.loads(response.body)
    archives = {item["storage_id"]: item for item in payload["linked_archives"]}

    healthy = archives["archive-healthy"]
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
    assert api.operator_checks[-1] == ("storage.disable", "archive-1")

    enabled = api.dispatch(
        "POST", "/api/v1/operator/linked-archives/archive-1/enable", headers, b""
    )
    assert enabled.status == 200
    assert json.loads(enabled.body) == {
        "linked_archive": {"storage_id": "archive-1", "enabled": True}
    }
    assert api._linked_storage.state["archive-1"] is True
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
