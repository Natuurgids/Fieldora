"""Operator-only linked archive health projection and lifecycle controls.

The existing Operator routes have already passed the normal authentication boundary before
this mixin enriches or extends them. Archive routing is deliberately limited to opaque
storage/service identity and health; root aliases, filesystem paths and trust material are
never included.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.server.api import ApiResponse

_HEARTBEAT_STALE_SECONDS = 120
_LINKED_ARCHIVE_EVENT_LIMIT = 100
_OPERATOR_JOB_LIMIT = 100
_MAX_OPERATOR_BODY = 16_384


class LinkedStorageOperatorApiMixin:
    """Append governed Operator projections and linked-archive lifecycle actions."""

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
            payload = json.loads(response.body)
            organization_id = str(payload.get("organization_id", "")).strip()
            checked_at = int(payload.get("checked_at_epoch", 0))
            if not organization_id or checked_at < 1:
                return response

            # The base Operator snapshot historically exposed only aggregate queue counts.
            # Enrich that same governed response with a bounded, payload-free recent-job
            # projection so operators can actually reconcile work that continues after a
            # browser session ends. Never expose job payload/result bodies or lease tokens.
            payload["jobs"] = _operator_job_snapshot(
                getattr(self, "_jobs", None),
                organization_id,
                payload.get("jobs"),
            )

            repository = getattr(self, "_linked_storage", None)
            operator = getattr(self, "_operator", None)
            connect_factory = getattr(repository, "connect_factory", None)
            if repository is not None and operator is not None and connect_factory is not None:
                payload["linked_archives"] = _linked_archive_health(
                    connect_factory,
                    operator,
                    organization_id,
                    checked_at,
                )
                payload["linked_archive_events"] = _linked_archive_events(
                    connect_factory,
                    organization_id,
                )
            return ApiResponse.json(200, payload)

        if method == "POST" and response.status == 404:
            if route.path == "/api/v1/operator/linked-storage-services/prepare-id":
                identity = self._operator_identity(headers)
                if isinstance(identity, ApiResponse):
                    return identity
                if not self._allow_operator(  # type: ignore[attr-defined]
                    identity, headers, "service.enroll", ""
                ):
                    return ApiResponse.json(403, {"error": "forbidden"})
                return ApiResponse.json(200, {"service_id": str(uuid4())})

            if route.path == "/api/v1/operator/linked-storage-services":
                identity = self._operator_identity(headers)
                if isinstance(identity, ApiResponse):
                    return identity
                if not self._allow_operator(  # type: ignore[attr-defined]
                    identity, headers, "service.enroll", ""
                ):
                    return ApiResponse.json(403, {"error": "forbidden"})
                operator = getattr(self, "_operator", None)
                if operator is None:
                    return ApiResponse.json(503, {"error": "operator_unavailable"})
                if len(body) > _MAX_OPERATOR_BODY:
                    return ApiResponse.json(400, {"error": "invalid_service"})
                try:
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError("service body must be an object")
                    service_id = _prepared_service_id(str(data["service_id"]))
                    item = operator.enroll(
                        organization_id=identity.organization_id,
                        name=str(data["name"]),
                        service_type="linked-storage",
                        node_name=str(data["node_name"]),
                        software_version=str(data.get("software_version", "")),
                        configuration_sha256=str(data.get("configuration_sha256", "")),
                        certificate_serial=str(data["certificate_serial"]),
                        certificate_not_after_epoch=int(data["certificate_not_after_epoch"]),
                        service_id=service_id,
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    return ApiResponse.json(400, {"error": "invalid_service"})
                return ApiResponse.json(201, {"service": item.as_dict()})

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
        identity = self._operator_identity(headers)
        if isinstance(identity, ApiResponse):
            return identity
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

    def _operator_identity(self, headers: dict[str, str]) -> Any | ApiResponse:
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        return identity


def _prepared_service_id(value: str) -> str:
    normalized = value.strip().casefold()
    parsed = UUID(normalized)
    canonical = str(parsed)
    if normalized != canonical:
        raise ValueError("linked storage service id must be a canonical UUID")
    return canonical


def _operator_job_snapshot(
    jobs: Any,
    organization_id: str,
    aggregate: object,
) -> dict[str, object]:
    """Return bounded Operator-safe job metadata for SQLite or PostgreSQL queues."""

    base = dict(aggregate) if isinstance(aggregate, dict) else {}
    database_path = getattr(jobs, "_database_path", None)
    if isinstance(database_path, Path) and database_path.is_file():
        connection = sqlite3.connect(database_path)
        try:
            rows = connection.execute(
                "SELECT job_id,job_type,project_id,status,attempts,created_at_utc,"
                "updated_at_utc,lease_owner FROM server_jobs "
                "WHERE organization_id=? ORDER BY updated_at_utc DESC,job_id LIMIT ?",
                (organization_id, _OPERATOR_JOB_LIMIT),
            ).fetchall()
        finally:
            connection.close()
        base["recent"] = [_operator_job_row(row) for row in rows]
        return base

    connect = getattr(jobs, "_connect", None)
    if callable(connect):
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT job_id,job_type,project_id,status,attempts,created_at_utc,"
                    "updated_at_utc,lease_owner FROM server_jobs "
                    "WHERE organization_id=%s ORDER BY updated_at_utc DESC,job_id LIMIT %s",
                    (organization_id, _OPERATOR_JOB_LIMIT),
                )
                rows = cursor.fetchall()
        base["recent"] = [_operator_job_row(row) for row in rows]
        return base

    base.setdefault("recent", [])
    return base


def _operator_job_row(row: Any) -> dict[str, object]:
    return {
        "job_id": str(row[0]),
        "job_type": str(row[1]),
        "project_id": str(row[2] or ""),
        "status": str(row[3]),
        "attempts": int(row[4]),
        "created_at_utc": _operator_timestamp(row[5]),
        "updated_at_utc": _operator_timestamp(row[6]),
        "lease_owner": str(row[7] or ""),
    }


def _operator_timestamp(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _linked_archive_events(
    connect_factory: Any,
    organization_id: str,
) -> list[dict[str, object]]:
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT storage_id,actor_id,event_type,occurred_at "
                "FROM linked_storage_source_events_pg "
                "WHERE organization_id=%s "
                "ORDER BY sequence DESC LIMIT %s",
                (organization_id, _LINKED_ARCHIVE_EVENT_LIMIT),
            )
            rows = cursor.fetchall()
    return [
        {
            "storage_id": str(row[0]),
            "actor_id": str(row[1]),
            "event_type": str(row[2]),
            "occurred_at": (
                row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3])
            ),
        }
        for row in rows
    ]


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
