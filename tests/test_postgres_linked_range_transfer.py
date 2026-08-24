from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from uuid import uuid4

import pytest

from natureai_next.server.postgres_linked_range_transfer import PostgresLinkedRangeTransfers
from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
)


def _connect():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn)


def _seed():
    connect = _connect()
    repository = PostgresLinkedStorageRepository(connect)
    suffix = uuid4().hex
    source = StorageSourceRegistration(
        f"storage-{suffix}",
        f"org-{suffix}",
        f"service-{suffix}",
        "Archive",
        f"archive-{suffix}",
        True,
    )
    repository.register_source(source)
    item = StorageCatalogueItem(
        object_id="object-1",
        relative_path="expedition/original.bin",
        filename="original.bin",
        mime_type="application/octet-stream",
        size_bytes=32,
        modified_ns=123456,
        state=StorageObjectState.AVAILABLE,
        thumbnail_state=PreviewState.UNSUPPORTED,
        project_id="project-1",
    )
    batch = StorageCatalogueBatch(
        batch_id=str(uuid4()),
        storage_id=source.storage_id,
        organization_id=source.organization_id,
        service_id=source.service_id,
        scan_id=str(uuid4()),
        sequence=1,
        final=True,
        checkpoint="",
        items=(item,),
    )
    repository.apply_catalogue_batch(replace(batch, batch_sha256=batch.calculated_sha256()))
    media = repository.browse(source.organization_id, source.storage_id)[0]
    return repository, PostgresLinkedRangeTransfers(connect), source, media


@pytest.mark.integration
def test_range_request_claim_upload_and_result_are_identity_bound() -> None:
    _repository, transfers, source, media = _seed()
    request_id = transfers.request_range(
        media_id=media.media_id,
        organization_id=source.organization_id,
        requested_by="researcher-1",
        start_byte=4,
        end_byte=11,
    )
    assert transfers.request_range(
        media_id=media.media_id,
        organization_id=source.organization_id,
        requested_by="researcher-1",
        start_byte=4,
        end_byte=11,
    ) == request_id

    leases = transfers.claim(
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="range-worker-1",
    )
    assert len(leases) == 1
    lease = leases[0]
    assert lease.request_id == request_id
    assert lease.object_id == "object-1"
    assert lease.start_byte == 4
    assert lease.end_byte == 11
    assert lease.total_size == 32

    payload = b"abcdefgh"
    digest = hashlib.sha256(payload).hexdigest()
    with pytest.raises(PermissionError, match="identity"):
        transfers.put_leased_range(
            request_id=request_id,
            media_id=media.media_id,
            storage_id=source.storage_id,
            organization_id=source.organization_id,
            service_id=source.service_id,
            worker_id="other-worker",
            start_byte=4,
            end_byte=11,
            sha256=digest,
            payload=payload,
        )

    stored = transfers.put_leased_range(
        request_id=request_id,
        media_id=media.media_id,
        storage_id=source.storage_id,
        organization_id=source.organization_id,
        service_id=source.service_id,
        worker_id="range-worker-1",
        start_byte=4,
        end_byte=11,
        sha256=digest,
        payload=payload,
    )
    assert stored.payload == payload
    assert stored.sha256 == digest
    assert transfers.result(request_id, source.organization_id, "other-user") is None
    result = transfers.result(request_id, source.organization_id, "researcher-1")
    assert result is not None
    assert result.state == "ready"
    assert result.payload == payload


@pytest.mark.integration
def test_range_request_rejects_oversize_and_out_of_bounds_ranges() -> None:
    _repository, transfers, source, media = _seed()
    with pytest.raises(ValueError, match="exceeds original size"):
        transfers.request_range(
            media_id=media.media_id,
            organization_id=source.organization_id,
            requested_by="researcher-1",
            start_byte=0,
            end_byte=32,
        )
    with pytest.raises(ValueError, match="invalid"):
        transfers.request_range(
            media_id=media.media_id,
            organization_id=source.organization_id,
            requested_by="researcher-1",
            start_byte=0,
            end_byte=4 * 1024 * 1024,
        )


@pytest.mark.integration
def test_disabled_source_cannot_create_new_range_request() -> None:
    repository, transfers, source, media = _seed()
    with repository.connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE linked_storage_sources_pg SET enabled=FALSE WHERE storage_id=%s",
                (source.storage_id,),
            )
    with pytest.raises(KeyError):
        transfers.request_range(
            media_id=media.media_id,
            organization_id=source.organization_id,
            requested_by="researcher-1",
            start_byte=0,
            end_byte=7,
        )
