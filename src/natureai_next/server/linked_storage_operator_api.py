"""Operator-only linked archive health projection and lifecycle controls.

The existing Operator routes have already passed the normal authentication boundary before
this mixin enriches or extends them. Archive routing is deliberately limited to opaque
storage/service identity and health; root aliases, filesystem paths and trust material are
never included.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.server.api import ApiResponse

_HEARTBEAT_STALE_SECONDS = 120


class LinkedStorageOperatorApiMixin:
    """Append linked archive health and expose PBAC-gated archive enable/disable actions."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)  # type: ignore[misc]
        route = urlsplit(target)
        if (
            method == "GET"
            and route.path == "/api/v1/operator/overview"
            and response.status == 200
        ):
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

        if method != "POST" or response.status != 404:
            return response
        suffix = route.path.removeprefix("/api/v1/operator/linked-archives/")
        parts = [part for part in suffix.split("/") if part]
        if len(parts) != 2 or route.path == suffix:
            return response
        storage_id, operation = parts
        enabled_by_operation = {"enable": True, "disable": False}
        if operation not in enabled_by_operation or not storage_id or len(storage_id) > 512:
            return response

        repository = getattr(self, "_linked_storage", None)
        set_source_enabled = getattr(repository, "set_source_enabled", None)
        if repository is None or set_source_enabled is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        action = f"storage.{operation}"
        if not self._allow_operator(  # type: ignore[attr-defined]
            identity, headers, action, storage_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        enabled = enabled_by_operation[operation]
        try:
            changed = set_source_enabled(
                storage_id,
                identity.organization_id,
                enabled,
                actor_id=identity.identity_id,
            )
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_linked_archive_lifecycle"})
        if not changed:
            return ApiResponse.json(404, {"error": "linked_archive_not_found"})
        return ApiResponse.json(
            200,
            {
                "linked_archive": {
                    "storage_id": storage_id,
                    "enabled": enabled,
                }
            },
        )


def _linked_archive_health(
    connect_factory: Any,
    operator: Any,
    organization_id: str,
    checked_at_epoch: int,
) -> list[dict[str, object]]:
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT storage_id,service_id,display_name,read_only,enabled "
                "FROM linked_storage_sources_pg "
                "WHERE organization_id=%s "
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
                "enabled": bool(row[4]),
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
