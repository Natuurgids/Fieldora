from __future__ import annotations

import json
import time
from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_sources_api import (
    LinkedStorageSourcesApiMixin,
    _availability,
)


class _Cursor:
    def __init__(self) -> None:
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _sql: str, parameters: tuple[str]) -> None:
        self.parameters = parameters

    def fetchall(self):
        return [("archive-1", "Primary research archive", True, "storage-service-1")]


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self._cursor


class _Repository:
    def __init__(self) -> None:
        self.cursor = _Cursor()

    def connect_factory(self):
        return _Connection(self.cursor)


@dataclass(frozen=True)
class _Identity:
    organization_id: str


@dataclass(frozen=True)
class _Service:
    state: str
    last_heartbeat_epoch: int


class _Operator:
    def __init__(self, service: _Service | None) -> None:
        self._service = service

    def service(self, service_id: str):
        assert service_id == "storage-service-1"
        return self._service


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(404, {"error": "not_found"})


class _IdentityApi(_BaseApi):
    def _linked_storage_identity(self, headers: dict[str, str]):
        if headers.get("authorization") != "Bearer good-token":
            return None, ApiResponse.json(401, {"error": "unauthorized"})
        return _Identity("org-1"), None


class _Api(LinkedStorageSourcesApiMixin, _IdentityApi):
    def __init__(self, operator=None) -> None:
        self._linked_storage = _Repository()
        if operator is not None:
            self._operator = operator


def test_source_discovery_is_organization_scoped_and_discloses_only_safe_fields() -> None:
    api = _Api()
    response = api.dispatch(
        "GET",
        "/api/v1/linked-storage/sources",
        {"authorization": "Bearer good-token"},
        b"",
    )
    payload = json.loads(response.body)
    assert response.status == 200
    assert payload == {
        "items": [
            {
                "storage_id": "archive-1",
                "display_name": "Primary research archive",
                "read_only": True,
                "availability": "unknown",
            }
        ],
        "count": 1,
    }
    assert api._linked_storage.cursor.parameters == ("org-1",)
    serialized = response.body.decode()
    assert "service_id" not in serialized
    assert "storage-service-1" not in serialized
    assert "heartbeat" not in serialized
    assert "root_alias" not in serialized
    assert "root_path" not in serialized
    assert "certificate" not in serialized


def test_source_availability_is_coarse_and_never_discloses_service_health_details() -> None:
    now = int(time.time())
    assert _availability(_Operator(_Service("active", now - 10)), "storage-service-1", now) == "online"
    assert _availability(_Operator(_Service("active", now - 121)), "storage-service-1", now) == "stale"
    assert _availability(_Operator(_Service("stopped", now - 10)), "storage-service-1", now) == "unavailable"
    assert _availability(_Operator(None), "storage-service-1", now) == "unavailable"
    assert _availability(None, "storage-service-1", now) == "unknown"

    response = _Api(_Operator(_Service("active", now - 10))).dispatch(
        "GET",
        "/api/v1/linked-storage/sources",
        {"authorization": "Bearer good-token"},
        b"",
    )
    payload = json.loads(response.body)
    assert payload["items"][0]["availability"] == "online"
    serialized = response.body.decode()
    assert "storage-service-1" not in serialized
    assert "heartbeat" not in serialized


def test_source_discovery_requires_authentication() -> None:
    response = _Api().dispatch("GET", "/api/v1/linked-storage/sources", {}, b"")
    assert response.status == 401


def test_non_source_route_delegates() -> None:
    response = _Api().dispatch(
        "GET", "/api/v1/other", {"authorization": "Bearer good-token"}, b""
    )
    assert response.status == 404
