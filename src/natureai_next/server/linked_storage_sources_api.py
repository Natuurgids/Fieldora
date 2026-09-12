"""Safe browser discovery of organization-linked storage sources.

This endpoint intentionally exposes only opaque source identity, display metadata and a
coarse availability classification. Storage-service routing, heartbeat details, root
aliases, mount paths and credentials remain internal.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_HEARTBEAT_STALE_SECONDS = 120


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
            items = _source_rows(
                connect_factory,
                identity.organization_id,
                getattr(self, "_operator", None),
            )
        except Exception:
            return ApiResponse.json(503, {"error": "linked_storage_source_discovery_unavailable"})
        return ApiResponse.json(200, {"items": items, "count": len(items)})


def _source_rows(
    connect_factory: Any,
    organization_id: str,
    operator: Any = None,
) -> list[dict[str, object]]:
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT storage_id,display_name,read_only,service_id "
                "FROM linked_storage_sources_pg "
                "WHERE organization_id=%s AND enabled=TRUE "
                "ORDER BY display_name,storage_id LIMIT 500",
                (organization_id,),
            )
            rows = cursor.fetchall()
    now_epoch = int(time.time())
    return [
        {
            "storage_id": str(row[0]),
            "display_name": str(row[1]),
            "read_only": bool(row[2]),
            "availability": _availability(operator, str(row[3]), now_epoch),
        }
        for row in rows
    ]


def _availability(operator: Any, service_id: str, now_epoch: int) -> str:
    if operator is None:
        return "unknown"
    service = operator.service(service_id)
    if service is None or service.state != "active":
        return "unavailable"
    if now_epoch - int(service.last_heartbeat_epoch) > _HEARTBEAT_STALE_SECONDS:
        return "stale"
    return "online"
