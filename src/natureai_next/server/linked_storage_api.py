"""Governed browser API for externally stored scientific media.

The browser sees Fieldora media identities and relative catalogue metadata only. Storage
service routing, root aliases, mount paths, and credentials remain outside this API.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.postgres_linked_preview_store import LinkedPreviewObject
from natureai_next.server.postgres_linked_range_transfer import (
    PostgresLinkedRangeTransfers,
    range_retry_after_seconds,
)
from natureai_next.server.postgres_linked_storage import ServerLinkedMedia


class LinkedStorageRepository(Protocol):
    @property
    def connect_factory(self): ...

    def source(self, storage_id: str) -> Any | None: ...

    def media(self, media_id: str) -> ServerLinkedMedia | None: ...

    def browse(
        self,
        organization_id: str,
        storage_id: str,
        prefix: str = "",
        limit: int = 200,
    ) -> tuple[ServerLinkedMedia, ...]: ...

    def request_preview(
        self,
        *,
        media_id: str,
        organization_id: str,
        priority: int,
        reason: str,
        requested_by: str,
    ) -> bool: ...

    def preview(self, media_id: str) -> LinkedPreviewObject | None: ...


class LinkedStorageApiMixin:
    """Route linked-storage catalogue operations before the existing API chain."""

    _linked_storage: LinkedStorageRepository | None
    _linked_range_transfers: PostgresLinkedRangeTransfers | Any | None = None

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if route.path == "/api/v1/linked-storage/browse" and method == "GET":
            return self._linked_storage_browse(headers, route.query)
        if route.path == "/api/v1/linked-storage/previews" and method == "POST":
            return self._linked_storage_request_previews(headers, body)
        if route.path == "/api/v1/linked-storage/thumbnail" and method == "GET":
            return self._linked_storage_thumbnail(headers, route.query)
        if route.path == "/api/v1/linked-storage/ranges" and method == "POST":
            return self._linked_storage_request_range(headers, body)
        if route.path == "/api/v1/linked-storage/ranges" and method == "GET":
            return self._linked_storage_range(headers, route.query)
        return super().dispatch(method, target, headers, body)  # type: ignore[misc]

    def _linked_storage_identity(self, headers: dict[str, str]):
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return None, ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )
        return identity, None

    def _linked_range_store(self):
        if self._linked_range_transfers is not None:
            return self._linked_range_transfers
        if self._linked_storage is None:
            return None
        factory = getattr(self._linked_storage, "connect_factory", None)
        if factory is None:
            return None
        self._linked_range_transfers = PostgresLinkedRangeTransfers(factory)
        return self._linked_range_transfers

    def _linked_storage_browse(
        self, headers: dict[str, str], query_string: str
    ) -> ApiResponse:
        if self._linked_storage is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        identity, error = self._linked_storage_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        query = parse_qs(query_string)
        storage_id = query.get("storage_id", [""])[0].strip()
        prefix = query.get("prefix", [""])[0].strip()
        try:
            limit = int(query.get("limit", ["200"])[0])
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_linked_storage_query"})
        if not storage_id or limit < 1:
            return ApiResponse.json(400, {"error": "invalid_linked_storage_query"})
        records = self._linked_storage.browse(
            identity.organization_id, storage_id, prefix, min(limit, 1000)
        )
        disclosed = [
            _linked_media_payload(record)
            for record in records
            if self._linked_storage_allowed(identity, headers, record)
        ]
        return ApiResponse.json(
            200,
            {
                "items": disclosed,
                "count": len(disclosed),
                "storage_id": storage_id,
                "prefix": prefix,
            },
        )

    def _linked_storage_request_previews(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._linked_storage is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        if len(body) > 256 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        identity, error = self._linked_storage_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        try:
            data = json.loads(body)
            media_ids = data["media_ids"]
            if not isinstance(media_ids, list) or not 1 <= len(media_ids) <= 500:
                raise ValueError
            normalized = tuple(dict.fromkeys(str(item).strip() for item in media_ids))
            if not normalized or any(not item or len(item) > 512 for item in normalized):
                raise ValueError
            priority = int(data.get("priority", 100))
            reason = str(data.get("reason", "visible-directory")).strip()
            if not reason or len(reason) > 120:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_preview_request"})
        queued: list[str] = []
        unavailable: list[str] = []
        for media_id in normalized:
            record = self._linked_storage.media(media_id)
            if (
                record is None
                or record.organization_id != identity.organization_id
                or not self._linked_storage_allowed(identity, headers, record)
            ):
                unavailable.append(media_id)
                continue
            if self._linked_storage.request_preview(
                media_id=media_id,
                organization_id=identity.organization_id,
                priority=max(0, min(priority, 1000)),
                reason=reason,
                requested_by=identity.identity_id,
            ):
                queued.append(media_id)
        return ApiResponse.json(
            202,
            {
                "queued_media_ids": queued,
                "unavailable_media_ids": unavailable,
                "queued_count": len(queued),
            },
        )

    def _linked_storage_thumbnail(
        self, headers: dict[str, str], query_string: str
    ) -> ApiResponse:
        if self._linked_storage is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        identity, error = self._linked_storage_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        query = parse_qs(query_string)
        media_id = query.get("media_id", [""])[0].strip()
        if not media_id or len(media_id) > 512:
            return ApiResponse.json(400, {"error": "invalid_thumbnail_query"})
        record = self._linked_storage.media(media_id)
        if (
            record is None
            or record.organization_id != identity.organization_id
            or not self._linked_storage_allowed(identity, headers, record)
        ):
            return ApiResponse.json(404, {"error": "linked_thumbnail_not_found"})
        preview = self._linked_storage.preview(media_id)
        if preview is None:
            return ApiResponse.json(404, {"error": "linked_thumbnail_not_ready"})
        return ApiResponse(
            200,
            preview.payload,
            content_type=preview.mime_type,
            headers=(("ETag", f'"{preview.sha256}"'), ("Content-Disposition", "inline")),
        )

    def _linked_storage_request_range(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._linked_storage is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        if len(body) > 64 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        store = self._linked_range_store()
        if store is None:
            return ApiResponse.json(503, {"error": "linked_range_unavailable"})
        identity, error = self._linked_storage_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        try:
            data = json.loads(body)
            media_id = str(data["media_id"]).strip()
            start = int(data["start_byte"])
            end = int(data["end_byte"])
            if not media_id or len(media_id) > 512:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_range_request"})
        record = self._linked_storage.media(media_id)
        if (
            record is None
            or record.organization_id != identity.organization_id
            or not self._linked_storage_allowed(identity, headers, record)
        ):
            return ApiResponse.json(404, {"error": "linked_original_not_found"})
        try:
            request_id = store.request_range(
                media_id=media_id,
                organization_id=identity.organization_id,
                requested_by=identity.identity_id,
                start_byte=start,
                end_byte=end,
            )
        except (KeyError, ValueError):
            return ApiResponse.json(416, {"error": "linked_range_not_satisfiable"})
        return ApiResponse.json(
            202,
            {
                "request_id": request_id,
                "media_id": media_id,
                "start_byte": start,
                "end_byte": end,
                "state": "pending",
            },
        )

    def _linked_storage_range(
        self, headers: dict[str, str], query_string: str
    ) -> ApiResponse:
        if self._linked_storage is None:
            return ApiResponse.json(503, {"error": "linked_storage_unavailable"})
        store = self._linked_range_store()
        if store is None:
            return ApiResponse.json(503, {"error": "linked_range_unavailable"})
        identity, error = self._linked_storage_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        request_id = parse_qs(query_string).get("request_id", [""])[0].strip()
        if not request_id or len(request_id) > 128:
            return ApiResponse.json(400, {"error": "invalid_range_query"})
        result = store.result(request_id, identity.organization_id, identity.identity_id)
        if result is None:
            return ApiResponse.json(404, {"error": "linked_range_not_found"})
        record = self._linked_storage.media(result.media_id)
        if (
            record is None
            or record.organization_id != identity.organization_id
            or not self._linked_storage_allowed(identity, headers, record)
        ):
            return ApiResponse.json(404, {"error": "linked_range_not_found"})
        if result.state != "ready":
            pending = ApiResponse.json(
                202,
                {
                    "request_id": request_id,
                    "media_id": result.media_id,
                    "state": result.state,
                },
            )
            return ApiResponse(
                pending.status,
                pending.body,
                pending.content_type,
                (("Retry-After", str(range_retry_after_seconds(result))),),
            )
        return ApiResponse(
            206,
            result.payload,
            content_type=result.mime_type,
            headers=(
                ("Accept-Ranges", "bytes"),
                ("Content-Range", f"bytes {result.start_byte}-{result.end_byte}/{result.total_size}"),
                ("ETag", f'"{result.sha256}"'),
                ("Content-Disposition", "attachment"),
            ),
        )

    def _linked_storage_allowed(
        self,
        identity: Any,
        headers: dict[str, str],
        record: ServerLinkedMedia,
    ) -> bool:
        if self._linked_storage is None or self._linked_storage.source(record.storage_id) is None:
            return False
        decision = self._decisions.decide(  # type: ignore[attr-defined]
            AccessRequest(
                identity.identity_id,
                "view",
                "asset",
                record.media_id,
                identity.organization_id,
                record.project_id,
                headers.get("x-fieldora-purpose", "research"),
                attributes={"storage_id": record.storage_id, "linked": "true"},
            )
        )
        return decision.allowed


def _linked_media_payload(record: ServerLinkedMedia) -> dict[str, Any]:
    return {
        "media_id": record.media_id,
        "storage_id": record.storage_id,
        "relative_path": record.relative_path,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "modified_ns": record.modified_ns,
        "state": record.object_state.value,
        "sha256": record.sha256,
        "thumbnail_state": record.thumbnail_state.value,
        "thumbnail_etag": record.thumbnail_etag,
        "project_id": record.project_id,
        "metadata": record.metadata,
    }
