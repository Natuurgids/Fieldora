"""Safe browser discovery of organization-linked storage sources.

This endpoint intentionally exposes only opaque source identity and display metadata.
Storage-service routing, root aliases, mount paths and credentials remain internal.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


class LinkedStorageSourcesApiMixin:
    """List enabled linked sources for the authenticated organization."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if urlsplit(target).path == "/api/v1/linked-storage/sources" and method == "GET":
            return self._linked_storage_sources(headers)
        return super().dispatch(method, target, headers, body)  # type: ignore[misc]

    def _linked_storage_sources(self, headers: dict[str, str]) -> ApiResponse:
        repository = getattr(self, "_linked_storage", None)
        if repository is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        identity, error = self._linked_storage_identity(headers)  # type: ignore[attr-defined]
        if error is not None:
            return error
        assert identity is not None
        connect_factory = getattr(repository, "connect_factory", None)
        if connect_factory is None:
            return ApiResponse.json(503, {"error": "linked_storage_source_discovery_unavailable"})
        try:
            items = _source_rows(connect_factory, identity.organization_id)
        except Exception:
            return ApiResponse.json(503, {"error": "linked_storage_source_discovery_unavailable"})
        return ApiResponse.json(200, {"items": items, "count": len(items)})


def _source_rows(connect_factory: Any, organization_id: str) -> list[dict[str, object]]:
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT storage_id,display_name,read_only "
                "FROM linked_storage_sources_pg "
                "WHERE organization_id=%s AND enabled=TRUE "
                "ORDER BY display_name,storage_id LIMIT 500",
                (organization_id,),
            )
            rows = cursor.fetchall()
    return [
        {
            "storage_id": str(row[0]),
            "display_name": str(row[1]),
            "read_only": bool(row[2]),
        }
        for row in rows
    ]
