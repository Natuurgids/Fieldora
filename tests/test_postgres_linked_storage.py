from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

import pytest

from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
)


def _repository() -> PostgresLinkedStorageRepository:
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return PostgresLinkedStorageRepository(lambda: psycopg.connect(dsn))


def _source(suffix: str) -> StorageSourceRegistration:
    return StorageSourceRegistration(
        storage_id=f"storage-{suffix}",
        organization_id=f"org-{suffix}",
        service_id=f"service-{suffix}",
        display_name="Scientific archive",
        root_alias=f"archive-{suffix}",
        read_only=True,
    )


def _item(object_id: str = "object-1", path: str = "Amazon/day-01/image-1.jpg") -> StorageCatalogueItem:
    return StorageCatalogueItem(
        object_id=object_id,
        relative_path=path,
        filename=path.rsplit("/", 1)[-1],
        mime_type="image/jpeg",
        size_bytes=12_345,
        modified_ns=123456789,
        state=StorageObjectState.AVAILABLE,
        thumbnail_state=PreviewState.MISSING,
        project_id="project-1",
    )


def _signed_batch(
    source: StorageSourceRegistration,
    *,
    scan_id: str,
    sequence: int,
    items: tuple[StorageCatalogueItem, ...],
    previous: str = "",
    final: bool = False,
) -> StorageCatalogueBatch:
    batch = StorageCatalogueBatch(
        batch_id=str(uuid4()),
        storage_id=source.storage_id,
        organization_id=source.organization_id,
        service_id=source.service_id,
        scan_id=scan_id,
        sequence=sequence,
        final=final,
        checkpoint="" if final else items[-1].relative_path,
        items=items,
        previous_batch_sha256=previous,
    )
    return replace(batch, batch_sha256=batch.calculated_sha256())


@pytest.mark.integration
def test_postgres_catalogue_is_idempotent_and_preserves_media_identity() -> None:
    repository = _repository()
    suffix = uuid4().hex
    source = _source(suffix)
    repository.register_source(source)
    scan_id = str(uuid4())
    first = _signed_batch(source, scan_id=scan_id, sequence=1, items=(_item(),))

    assert repository.apply_catalogue_batch(first) == (1, 0)
    assert repository.apply_catalogue_batch(first) == (0, 0)
    records = repository.browse(source.organization_id, source.storage_id)
    assert len(records) == 1
    media_id = records[0].media_id
    assert records[0].project_id == "project-1"

    second = _signed_batch(
        source,
        scan_id=scan_id,
        sequence=2,
        previous=first.batch_sha256,
        final=True,
        items=(replace(_item(), size_bytes=54_321, project_id="project-2"),),
    )
    assert repository.apply_catalogue_batch(second) == (0, 1)
    records = repository.browse(source.organization_id, source.storage_id)
    assert len(records) == 1
    assert records[0].media_id == media_id
    assert records[0].size_bytes == 54_321
    assert records[0].project_id == "project-2"


@pytest.mark.integration
def test_postgres_catalogue_rejects_wrong_service_and_broken_hash_chain() -> None:
    repository = _repository()
    suffix = uuid4().hex
    source = _source(suffix)
    repository.register_source(source)
    scan_id = str(uuid4())

    wrong_service = replace(
        _signed_batch(source, scan_id=scan_id, sequence=1, items=(_item(),)),
        service_id="other-service",
    )
    wrong_service = replace(wrong_service, batch_sha256=wrong_service.calculated_sha256())
    with pytest.raises(ValueError, match="source identity mismatch"):
        repository.apply_catalogue_batch(wrong_service)

    first = _signed_batch(source, scan_id=scan_id, sequence=1, items=(_item(),))
    repository.apply_catalogue_batch(first)
    broken = _signed_batch(
        source,
        scan_id=scan_id,
        sequence=2,
        previous="0" * 64,
        final=True,
        items=(),
    )
    with pytest.raises(ValueError, match="hash chain mismatch"):
        repository.apply_catalogue_batch(broken)


@pytest.mark.integration
def test_interactive_preview_request_is_shared_and_deduplicated() -> None:
    repository = _repository()
    suffix = uuid4().hex
    source = _source(suffix)
    repository.register_source(source)
    batch = _signed_batch(
        source,
        scan_id=str(uuid4()),
        sequence=1,
        final=True,
        items=(_item(),),
    )
    repository.apply_catalogue_batch(batch)
    record = repository.browse(source.organization_id, source.storage_id)[0]

    assert repository.request_preview(
        media_id=record.media_id,
        organization_id=source.organization_id,
        priority=100,
        reason="visible-directory",
        requested_by="researcher-1",
    )
    assert repository.request_preview(
        media_id=record.media_id,
        organization_id=source.organization_id,
        priority=500,
        reason="opened-detail",
        requested_by="researcher-1",
    )
