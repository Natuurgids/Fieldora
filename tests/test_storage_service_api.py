from __future__ import annotations

import json
from dataclasses import replace

from natureai_next.server.operator_control import ServiceRecord, ServiceState
from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
)
from natureai_next.server.storage_service_api import LinkedStorageServiceApi


class _Operators:
    def __init__(self, service: ServiceRecord | None) -> None:
        self._service = service

    def service(self, service_id: str):
        if self._service is None or self._service.service_id != service_id:
            return None
        return self._service


class _Catalogue:
    def __init__(self, source: StorageSourceRegistration) -> None:
        self._source = source
        self.applied: list[StorageCatalogueBatch] = []
        self.registered: list[StorageSourceRegistration] = []

    def source(self, storage_id: str):
        return self._source if self._source.storage_id == storage_id else None

    def register_source(self, source: StorageSourceRegistration) -> None:
        self.registered.append(source)
        self._source = source

    def apply_catalogue_batch(self, batch: StorageCatalogueBatch):
        if not batch.verify():
            raise ValueError("catalogue batch digest is invalid")
        self.applied.append(batch)
        return 1, 0


class _Leases:
    def __init__(self) -> None:
        self.claims: list[dict] = []
        self.completions: list[dict] = []

    def claim(self, **kwargs):
        self.claims.append(kwargs)
        return ()

    def complete(self, **kwargs):
        self.completions.append(kwargs)
        return True


def _service(*, state: ServiceState = ServiceState.ACTIVE, serial: str = "ABCD") -> ServiceRecord:
    return ServiceRecord(
        service_id="storage-service-1",
        organization_id="org-1",
        name="Archive service",
        service_type="linked-storage",
        node_name="storage-node-1",
        state=state.value,
        software_version="5.4.0",
        configuration_sha256="",
        certificate_serial=serial,
        certificate_not_after_epoch=2_000_000_000,
        enrolled_at_epoch=1,
        last_heartbeat_epoch=1,
        drain_requested_epoch=0,
        stopped_at_epoch=0,
        revoked_at_epoch=0,
    )


def _source() -> StorageSourceRegistration:
    return StorageSourceRegistration(
        "archive-1", "org-1", "storage-service-1", "Archive", "primary-archive"
    )


def _api(service: ServiceRecord | None = None):
    catalogue = _Catalogue(_source())
    leases = _Leases()
    api = LinkedStorageServiceApi(catalogue, leases, _Operators(service or _service()))
    return api, catalogue, leases


def _headers(serial: str = "ABCD") -> dict[str, str]:
    return {"fieldora-peer-certificate-serial": serial}


def _catalogue_payload() -> dict:
    item = StorageCatalogueItem(
        object_id="obj-1",
        relative_path="Amazon/day-01/image.jpg",
        filename="image.jpg",
        mime_type="image/jpeg",
        size_bytes=123,
        modified_ns=456,
        state=StorageObjectState.AVAILABLE,
        project_id="project-1",
    )
    batch = StorageCatalogueBatch(
        batch_id="batch-1",
        storage_id="archive-1",
        organization_id="org-1",
        service_id="storage-service-1",
        scan_id="scan-1",
        sequence=1,
        final=True,
        checkpoint="",
        items=(item,),
    )
    batch = replace(batch, batch_sha256=batch.calculated_sha256())
    return {
        "batch_id": batch.batch_id,
        "storage_id": batch.storage_id,
        "organization_id": batch.organization_id,
        "service_id": batch.service_id,
        "scan_id": batch.scan_id,
        "sequence": batch.sequence,
        "final": batch.final,
        "checkpoint": batch.checkpoint,
        "previous_batch_sha256": batch.previous_batch_sha256,
        "batch_sha256": batch.batch_sha256,
        "items": [
            {
                "object_id": item.object_id,
                "relative_path": item.relative_path,
                "filename": item.filename,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "modified_ns": item.modified_ns,
                "state": item.state.value,
                "project_id": item.project_id,
            }
        ],
    }


def test_source_registration_requires_matching_active_storage_service() -> None:
    api, catalogue, _leases = _api()
    payload = json.dumps(
        {
            "storage_id": "archive-2",
            "organization_id": "org-1",
            "service_id": "storage-service-1",
            "display_name": "Secondary archive",
            "root_alias": "secondary-archive",
            "read_only": True,
        }
    ).encode()

    denied = api.dispatch("POST", "/internal/v1/storage/sources", _headers("FFFF"), payload)
    assert denied.status == 403
    assert catalogue.registered == []

    accepted = api.dispatch("POST", "/internal/v1/storage/sources", _headers(), payload)
    assert accepted.status == 200
    assert len(catalogue.registered) == 1
    assert catalogue.registered[0].root_alias == "secondary-archive"
    assert "root_path" not in json.loads(accepted.body)


def test_catalogue_requires_matching_active_service_certificate() -> None:
    api, catalogue, _leases = _api()
    payload = json.dumps(_catalogue_payload()).encode()

    missing = api.dispatch("POST", "/internal/v1/storage/catalogue", {}, payload)
    assert missing.status == 401

    mismatch = api.dispatch("POST", "/internal/v1/storage/catalogue", _headers("FFFF"), payload)
    assert mismatch.status == 403
    assert json.loads(mismatch.body)["error"] == "service_certificate_mismatch"
    assert catalogue.applied == []


def test_inactive_service_cannot_catalogue_or_claim_work() -> None:
    api, catalogue, leases = _api(_service(state=ServiceState.REVOKED))
    response = api.dispatch(
        "POST",
        "/internal/v1/storage/catalogue",
        _headers(),
        json.dumps(_catalogue_payload()).encode(),
    )
    assert response.status == 403
    assert json.loads(response.body)["error"] == "service_not_active"
    assert catalogue.applied == []

    claim = api.dispatch(
        "POST",
        "/internal/v1/storage/previews/claim",
        _headers(),
        json.dumps(
            {
                "service_id": "storage-service-1",
                "organization_id": "org-1",
                "storage_id": "archive-1",
                "worker_id": "preview-worker-1",
            }
        ).encode(),
    )
    assert claim.status == 403
    assert leases.claims == []


def test_valid_service_catalogue_preserves_project_scope() -> None:
    api, catalogue, _leases = _api()
    response = api.dispatch(
        "POST",
        "/internal/v1/storage/catalogue",
        _headers(),
        json.dumps(_catalogue_payload()).encode(),
    )
    assert response.status == 200
    assert len(catalogue.applied) == 1
    assert catalogue.applied[0].items[0].project_id == "project-1"


def test_valid_service_can_claim_and_complete_preview_lease() -> None:
    api, _catalogue, leases = _api()
    claim = api.dispatch(
        "POST",
        "/internal/v1/storage/previews/claim",
        _headers(),
        json.dumps(
            {
                "service_id": "storage-service-1",
                "organization_id": "org-1",
                "storage_id": "archive-1",
                "worker_id": "preview-worker-1",
                "limit": 20,
                "lease_seconds": 120,
            }
        ).encode(),
    )
    assert claim.status == 200
    assert leases.claims[0]["worker_id"] == "preview-worker-1"

    complete = api.dispatch(
        "POST",
        "/internal/v1/storage/previews/complete",
        _headers(),
        json.dumps(
            {
                "service_id": "storage-service-1",
                "organization_id": "org-1",
                "storage_id": "archive-1",
                "worker_id": "preview-worker-1",
                "media_id": "linked:archive-1:obj-1",
                "state": PreviewState.READY.value,
                "thumbnail_etag": "sha256:preview",
            }
        ).encode(),
    )
    assert complete.status == 200
    assert leases.completions[0]["state"] is PreviewState.READY
