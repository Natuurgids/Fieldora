"""Operator-only linked archive health projection.

The existing Operator overview has already passed infrastructure PBAC before this mixin
enriches it.  Archive routing is deliberately limited to service identity and health;
root aliases, filesystem paths and trust material are never included.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_HEARTBEAT_STALE_SECONDS = 120


class LinkedStorageOperatorApiMixin:
    """Append linked archive ownership/health to the protected Operator overview."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)  # type: ignore[misc]
        if (
            method != "GET"
            or urlsplit(target).path != "/api/v1/operator/overview"
            or response.status != 200
        ):
            return response
        repository = getattr(self, "_linked_storage", None)
        operator = getattr(self, "_operator", None)
        connect_factory = getattr(repository, "connect_factory", None)
        if repository is None or operator is None or connect_factory is None:
            return response
        payload = json.loads(response.body)
        organization_id = str(payload.get("organization_id", "")).strip()
        checked_at = int(payload.get("checked_at_epoch", 0))
        if not organization_id or checked_at < 1:
            return response
        payload["linked_archives"] = _linked_archive_health(
            connect_factory,
            operator,
            organization_id,
            checked_at,
        )
        return ApiResponse.json(200, payload)


def _linked_archive_health(
    connect_factory: Any,
    operator: Any,
    organization_id: str,
    checked_at_epoch: int,
) -> list[dict[str, object]]:
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT storage_id,service_id,display_name,read_only "
                "FROM linked_storage_sources_pg "
                "WHERE organization_id=%s AND enabled=TRUE "
                "ORDER BY display_name,storage_id LIMIT 500",
                (organization_id,),
            )
            rows = cursor.fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        service_id = str(row[1])
        service = operator.service(service_id)
        service_payload = None if service is None else service.as_dict(now_epoch=checked_at_epoch)
        heartbeat_age = (
            None
            if service_payload is None
            else int(service_payload["heartbeat_age_seconds"])
        )
        items.append(
            {
                "storage_id": str(row[0]),
                "display_name": str(row[2]),
                "read_only": bool(row[3]),
                "service_id": service_id,
                "service_name": "" if service is None else service.name,
                "node_name": "" if service is None else service.node_name,
                "service_state": "missing" if service is None else service.state,
                "heartbeat_age_seconds": heartbeat_age,
                "stale": (
                    service is None
                    or (
                        service.state == "active"
                        and heartbeat_age is not None
                        and heartbeat_age > _HEARTBEAT_STALE_SECONDS
                    )
                ),
            }
        )
    return items
