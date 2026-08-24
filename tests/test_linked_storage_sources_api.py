from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_sources_api import LinkedStorageSourcesApiMixin


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
        return [("archive-1", "Primary research archive", True)]


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


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(404, {"error": "not_found"})


class _IdentityApi(_BaseApi):
    def _linked_storage_identity(self, headers: dict[str, str]):
        if headers.get("authorization") != "Bearer good-token":
            return None, ApiResponse.json(401, {"error": "unauthorized"})
        return _Identity("org-1"), None


class _Api(LinkedStorageSourcesApiMixin, _IdentityApi):
    def __init__(self) -> None:
        self._linked_storage = _Repository()


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
            }
        ],
        "count": 1,
    }
    assert api._linked_storage.cursor.parameters == ("org-1",)
    serialized = response.body.decode()
    assert "service_id" not in serialized
    assert "root_alias" not in serialized
    assert "root_path" not in serialized
    assert "certificate" not in serialized


def test_source_discovery_requires_authentication() -> None:
    response = _Api().dispatch("GET", "/api/v1/linked-storage/sources", {}, b"")
    assert response.status == 401


def test_non_source_route_delegates() -> None:
    response = _Api().dispatch(
        "GET", "/api/v1/other", {"authorization": "Bearer good-token"}, b""
    )
    assert response.status == 404
