"""Internal mTLS-only API for linked storage services.

The transport injects peer-certificate metadata after a successful TLS handshake. This
API binds that certificate to the durable operator service record before accepting source
registrations, catalogue data, preview work, or bounded original-byte range transfers.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any, Protocol

from natureai_next.server.api import ApiResponse
from natureai_next.server.operator_control import OperatorRepository, ServiceState
from natureai_next.server.postgres_linked_preview import PostgresLinkedPreviewLeases
from natureai_next.server.postgres_linked_preview_store import PostgresLinkedPreviewStore
from natureai_next.server.postgres_linked_range_transfer import PostgresLinkedRangeTransfers
from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
)

_PEER_SERIAL = "fieldora-peer-certificate-serial"
_HEARTBEAT_INTERVAL_SECONDS = 60
_MAX_PREVIEW_BYTES = 2 * 1024 * 1024
_MAX_RANGE_BYTES = 4 * 1024 * 1024


class StorageServiceApplication(Protocol):
    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse: ...


class LinkedStorageServiceApi:
    def __init__(
        self,
        catalogue: PostgresLinkedStorageRepository,
        leases: PostgresLinkedPreviewLeases,
        operators: OperatorRepository,
        preview_store: PostgresLinkedPreviewStore | None = None,
        range_transfers: PostgresLinkedRangeTransfers | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._leases = leases
        self._operators = operators
        self._preview_store = preview_store
        self._range_transfers = range_transfers

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if target == "/internal/v1/storage/sources" and method == "POST":
            return self._register_source(headers, body)
        if target == "/internal/v1/storage/catalogue" and method == "POST":
            return self._catalogue_batch(headers, body)
        if target == "/internal/v1/storage/previews/claim" and method == "POST":
            return self._claim_previews(headers, body)
        if target == "/internal/v1/storage/previews/upload" and method == "PUT":
            return self._upload_preview(headers, body)
        if target == "/internal/v1/storage/previews/complete" and method == "POST":
            return self._complete_preview(headers, body)
        if target == "/internal/v1/storage/ranges/claim" and method == "POST":
            return self._claim_ranges(headers, body)
        if target == "/internal/v1/storage/ranges/upload" and method == "PUT":
            return self._upload_range(headers, body)
        return ApiResponse.json(404, {"error": "not_found"})

    def _service(
        self,
        headers: dict[str, str],
        *,
        service_id: str,
        organization_id: str,
    ):
        serial = headers.get(_PEER_SERIAL, "").strip().upper()
        if not serial:
            return None, ApiResponse.json(401, {"error": "client_certificate_required"})
        service = self._operators.service(service_id)
        if service is None:
            return None, ApiResponse.json(403, {"error": "service_not_enrolled"})
        if service.organization_id != organization_id:
            return None, ApiResponse.json(403, {"error": "service_organization_mismatch"})
        if service.certificate_serial.strip().upper() != serial:
            return None, ApiResponse.json(403, {"error": "service_certificate_mismatch"})
        if ServiceState(service.state) is not ServiceState.ACTIVE:
            return None, ApiResponse.json(403, {"error": "service_not_active"})
        if "storage" not in service.service_type.casefold():
            return None, ApiResponse.json(403, {"error": "service_type_forbidden"})
        now = int(time.time())
        if now - service.last_heartbeat_epoch >= _HEARTBEAT_INTERVAL_SECONDS:
            try:
                service = self._operators.heartbeat(service_id, now_epoch=now)
            except (KeyError, PermissionError):
                return None, ApiResponse.json(403, {"error": "service_not_active"})
        return service, None

    def _register_source(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if len(body) > 64 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = json.loads(body)
            source = StorageSourceRegistration(
                storage_id=str(data["storage_id"]).strip(),
                organization_id=str(data["organization_id"]).strip(),
                service_id=str(data["service_id"]).strip(),
                display_name=str(data["display_name"]).strip(),
                root_alias=str(data["root_alias"]).strip(),
                read_only=bool(data.get("read_only", True)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_storage_source"})
        _service, error = self._service(
            headers, service_id=source.service_id, organization_id=source.organization_id
        )
        if error is not None:
            return error
        try:
            self._catalogue.register_source(source)
        except ValueError as exc:
            return ApiResponse.json(409, {"error": "storage_source_rejected", "detail": str(exc)})
        return ApiResponse.json(
            200,
            {
                "storage_id": source.storage_id,
                "organization_id": source.organization_id,
                "service_id": source.service_id,
                "display_name": source.display_name,
                "read_only": source.read_only,
            },
        )

    def _catalogue_batch(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if len(body) > 8 * 1024 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            batch = _decode_batch(json.loads(body))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_catalogue_batch"})
        _service, error = self._service(
            headers, service_id=batch.service_id, organization_id=batch.organization_id
        )
        if error is not None:
            return error
        try:
            inserted, updated = self._catalogue.apply_catalogue_batch(batch)
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "catalogue_rejected", "detail": str(exc)})
        return ApiResponse.json(
            200,
            {
                "batch_id": batch.batch_id,
                "scan_id": batch.scan_id,
                "sequence": batch.sequence,
                "inserted": inserted,
                "updated": updated,
                "final": batch.final,
            },
        )

    def _claim_previews(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        try:
            data = json.loads(body)
            service_id = str(data["service_id"]).strip()
            organization_id = str(data["organization_id"]).strip()
            storage_id = str(data["storage_id"]).strip()
            worker_id = str(data["worker_id"]).strip()
            limit = int(data.get("limit", 50))
            lease_seconds = int(data.get("lease_seconds", 120))
            if not all((service_id, organization_id, storage_id, worker_id)):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_preview_claim"})
        error = self._authorize_source(headers, service_id, organization_id, storage_id)
        if error is not None:
            return error
        try:
            items = self._leases.claim(
                storage_id=storage_id,
                service_id=service_id,
                worker_id=worker_id,
                limit=limit,
                lease_seconds=lease_seconds,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "preview_claim_rejected", "detail": str(exc)})
        return ApiResponse.json(200, {"items": [asdict(item) for item in items]})

    def _upload_preview(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if self._preview_store is None:
            return ApiResponse.json(503, {"error": "preview_store_unavailable"})
        if not 1 <= len(body) <= _MAX_PREVIEW_BYTES:
            return ApiResponse.json(413, {"error": "preview_payload_size_invalid"})
        service_id, organization_id, storage_id, worker_id, media_id = _upload_identity(headers)
        digest = headers.get("fieldora-preview-sha256", "").strip().casefold()
        mime_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if not all((service_id, organization_id, storage_id, worker_id, media_id, digest)):
            return ApiResponse.json(400, {"error": "invalid_preview_upload_identity"})
        error = self._authorize_source(headers, service_id, organization_id, storage_id)
        if error is not None:
            return error
        try:
            stored = self._preview_store.put_leased_preview(
                media_id=media_id,
                storage_id=storage_id,
                organization_id=organization_id,
                service_id=service_id,
                worker_id=worker_id,
                mime_type=mime_type,
                sha256=digest,
                payload=body,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "preview_upload_rejected", "detail": str(exc)})
        return ApiResponse.json(
            200,
            {
                "media_id": stored.media_id,
                "thumbnail_etag": stored.sha256,
                "size_bytes": stored.size_bytes,
                "state": PreviewState.READY.value,
            },
        )

    def _complete_preview(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        try:
            data = json.loads(body)
            service_id = str(data["service_id"]).strip()
            organization_id = str(data["organization_id"]).strip()
            storage_id = str(data["storage_id"]).strip()
            worker_id = str(data["worker_id"]).strip()
            media_id = str(data["media_id"]).strip()
            state = PreviewState(str(data["state"]))
            thumbnail_etag = str(data.get("thumbnail_etag", "")).strip()
            if not all((service_id, organization_id, storage_id, worker_id, media_id)):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_preview_completion"})
        error = self._authorize_source(headers, service_id, organization_id, storage_id)
        if error is not None:
            return error
        try:
            completed = self._leases.complete(
                media_id=media_id,
                storage_id=storage_id,
                service_id=service_id,
                worker_id=worker_id,
                state=state,
                thumbnail_etag=thumbnail_etag,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "preview_completion_rejected", "detail": str(exc)})
        if not completed:
            return ApiResponse.json(409, {"error": "preview_lease_not_owned"})
        return ApiResponse.json(200, {"media_id": media_id, "state": state.value})

    def _claim_ranges(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if self._range_transfers is None:
            return ApiResponse.json(503, {"error": "range_transfer_unavailable"})
        try:
            data = json.loads(body)
            service_id = str(data["service_id"]).strip()
            organization_id = str(data["organization_id"]).strip()
            storage_id = str(data["storage_id"]).strip()
            worker_id = str(data["worker_id"]).strip()
            limit = int(data.get("limit", 8))
            lease_seconds = int(data.get("lease_seconds", 120))
            if not all((service_id, organization_id, storage_id, worker_id)):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_range_claim"})
        error = self._authorize_source(headers, service_id, organization_id, storage_id)
        if error is not None:
            return error
        try:
            items = self._range_transfers.claim(
                storage_id=storage_id,
                service_id=service_id,
                worker_id=worker_id,
                limit=limit,
                lease_seconds=lease_seconds,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "range_claim_rejected", "detail": str(exc)})
        return ApiResponse.json(200, {"items": [asdict(item) for item in items]})

    def _upload_range(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if self._range_transfers is None:
            return ApiResponse.json(503, {"error": "range_transfer_unavailable"})
        if not 1 <= len(body) <= _MAX_RANGE_BYTES:
            return ApiResponse.json(413, {"error": "range_payload_size_invalid"})
        service_id, organization_id, storage_id, worker_id, media_id = _upload_identity(headers)
        request_id = headers.get("fieldora-range-request-id", "").strip()
        digest = headers.get("fieldora-range-sha256", "").strip().casefold()
        try:
            start = int(headers.get("fieldora-range-start", ""))
            end = int(headers.get("fieldora-range-end", ""))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_range_upload_identity"})
        if not all(
            (service_id, organization_id, storage_id, worker_id, media_id, request_id, digest)
        ):
            return ApiResponse.json(400, {"error": "invalid_range_upload_identity"})
        error = self._authorize_source(headers, service_id, organization_id, storage_id)
        if error is not None:
            return error
        try:
            result = self._range_transfers.put_leased_range(
                request_id=request_id,
                media_id=media_id,
                storage_id=storage_id,
                organization_id=organization_id,
                service_id=service_id,
                worker_id=worker_id,
                start_byte=start,
                end_byte=end,
                sha256=digest,
                payload=body,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            return ApiResponse.json(409, {"error": "range_upload_rejected", "detail": str(exc)})
        return ApiResponse.json(
            200,
            {
                "request_id": result.request_id,
                "media_id": result.media_id,
                "start_byte": result.start_byte,
                "end_byte": result.end_byte,
                "sha256": result.sha256,
                "state": result.state,
            },
        )

    def _authorize_source(
        self,
        headers: dict[str, str],
        service_id: str,
        organization_id: str,
        storage_id: str,
    ) -> ApiResponse | None:
        _service, error = self._service(
            headers, service_id=service_id, organization_id=organization_id
        )
        if error is not None:
            return error
        source = self._catalogue.source(storage_id)
        if source is None or source.organization_id != organization_id or source.service_id != service_id:
            return ApiResponse.json(403, {"error": "storage_source_forbidden"})
        return None


def _upload_identity(headers: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        headers.get("fieldora-service-id", "").strip(),
        headers.get("fieldora-organization-id", "").strip(),
        headers.get("fieldora-storage-id", "").strip(),
        headers.get("fieldora-worker-id", "").strip(),
        headers.get("fieldora-media-id", "").strip(),
    )


def _decode_batch(data: Any) -> StorageCatalogueBatch:
    if not isinstance(data, dict):
        raise ValueError("catalogue batch must be an object")
    items_data = data.get("items")
    if not isinstance(items_data, list) or len(items_data) > 10_000:
        raise ValueError("catalogue items must be a bounded list")
    items = tuple(_decode_item(item) for item in items_data)
    return StorageCatalogueBatch(
        batch_id=str(data["batch_id"]).strip(),
        storage_id=str(data["storage_id"]).strip(),
        organization_id=str(data["organization_id"]).strip(),
        service_id=str(data["service_id"]).strip(),
        scan_id=str(data["scan_id"]).strip(),
        sequence=int(data["sequence"]),
        final=bool(data["final"]),
        checkpoint=str(data.get("checkpoint", "")).strip(),
        items=items,
        previous_batch_sha256=str(data.get("previous_batch_sha256", "")).strip(),
        batch_sha256=str(data["batch_sha256"]).strip(),
    )


def _decode_item(data: Any) -> StorageCatalogueItem:
    if not isinstance(data, dict):
        raise ValueError("catalogue item must be an object")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("catalogue metadata must be an object")
    return StorageCatalogueItem(
        object_id=str(data["object_id"]).strip(),
        relative_path=str(data["relative_path"]).strip(),
        filename=str(data["filename"]).strip(),
        mime_type=str(data.get("mime_type", "application/octet-stream")).strip(),
        size_bytes=int(data["size_bytes"]),
        modified_ns=int(data["modified_ns"]),
        state=StorageObjectState(str(data.get("state", StorageObjectState.AVAILABLE.value))),
        sha256=str(data.get("sha256", "")).strip(),
        thumbnail_state=PreviewState(str(data.get("thumbnail_state", PreviewState.MISSING.value))),
        thumbnail_etag=str(data.get("thumbnail_etag", "")).strip(),
        project_id=str(data.get("project_id", "")).strip(),
        metadata=dict(metadata),
    )
