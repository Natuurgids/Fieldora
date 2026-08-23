from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

import pytest

from natureai_next.server.postgres_linked_preview import PostgresLinkedPreviewLeases
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


def _seed_preview() -> tuple[PostgresLinkedStorageRepository, PostgresLinkedPreviewLeases, StorageSourceRegistration, str]:
    connect = _connect()
    repository = PostgresLinkedStorageRepository(connect)
    leases = PostgresLinkedPreviewLeases(connect)
    suffix = uuid4().hex
    source = StorageSourceRegistration(
        storage_id=f"storage-{suffix}",
        organization_id=f"org-{suffix}",
        service_id=f"service-{suffix}",
        display_name="Scientific archive",
        root_alias=f"archive-{suffix}",
        read_only=True,
    )
    repository.register_source(source)
    item = StorageCatalogueItem(
        object_id="object-1",
        relative_path="Expedition/day-01/image-1.jpg",
        filename="image-1.jpg",
        mime_type="image/jpeg",
        size_bytes=12345,
        modified_ns=123456789,
        state=StorageObjectState.AVAILABLE,
        thumbnail_state=PreviewState.MISSING,
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
    repository.apply_catalogue_batch(
        replace(batch, batch_sha256=batch.calculated_sha256())
    )
    media = repository.browse(source.organization_id, source.storage_id)[0]
    assert repository.request_preview(
        media_id=media.media_id,
        organization_id=source.organization_id,
        priority=900,
        reason="opened-detail",
        requested_by="researcher-1",
    )
    return repository, leases, source, media.media_id


@pytest.mark.integration
def test_preview_claim_is_service_bound_and_marks_processing() -> None:
    repository, leases, source, media_id = _seed_preview()

    claimed = leases.claim(
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="worker-1",
        lease_seconds=120,
    )
    assert len(claimed) == 1
    assert claimed[0].media_id == media_id
    assert claimed[0].storage_id == source.storage_id
    assert claimed[0].object_id == "object-1"
    assert claimed[0].organization_id == source.organization_id
    assert claimed[0].priority == 900
    assert claimed[0].worker_id == "worker-1"

    media = repository.media(media_id)
    assert media is not None
    assert media.thumbnail_state is PreviewState.PROCESSING

    assert leases.claim(
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="worker-2",
    ) == ()


@pytest.mark.integration
def test_preview_claim_rejects_service_that_does_not_own_source() -> None:
    _repository, leases, source, _media_id = _seed_preview()
    with pytest.raises(PermissionError, match="different service"):
        leases.claim(
            storage_id=source.storage_id,
            service_id="other-service",
            worker_id="worker-1",
        )


@pytest.mark.integration
def test_preview_completion_requires_current_worker_and_updates_catalogue() -> None:
    repository, leases, source, media_id = _seed_preview()
    assert len(
        leases.claim(
            storage_id=source.storage_id,
            service_id=source.service_id,
            worker_id="worker-1",
        )
    ) == 1

    assert not leases.complete(
        media_id=media_id,
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="worker-2",
        state=PreviewState.READY,
        thumbnail_etag="etag-1",
    )
    assert leases.complete(
        media_id=media_id,
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="worker-1",
        state=PreviewState.READY,
        thumbnail_etag="etag-1",
    )

    media = repository.media(media_id)
    assert media is not None
    assert media.thumbnail_state is PreviewState.READY
    assert media.thumbnail_etag == "etag-1"
    assert leases.claim(
        storage_id=source.storage_id,
        service_id=source.service_id,
        worker_id="worker-3",
    ) == ()


@pytest.mark.integration
def test_preview_completion_rejects_non_terminal_state() -> None:
    _repository, leases, source, media_id = _seed_preview()
    with pytest.raises(ValueError, match="not terminal"):
        leases.complete(
            media_id=media_id,
            storage_id=source.storage_id,
            service_id=source.service_id,
            worker_id="worker-1",
            state=PreviewState.PROCESSING,
        )
