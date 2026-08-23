from __future__ import annotations

from dataclasses import replace

import pytest

from natureai_next.server.storage_exchange import (
    GovernedStorageRead,
    PreviewPriorityRequest,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
    authorization_digest,
)


def _item() -> StorageCatalogueItem:
    return StorageCatalogueItem(
        object_id="obj-1",
        relative_path="Expedition-A/Camera-1/IMG_0001.jpg",
        filename="IMG_0001.jpg",
        mime_type="image/jpeg",
        size_bytes=42_000_000,
        modified_ns=123456789,
        state=StorageObjectState.AVAILABLE,
    )


def test_storage_source_uses_opaque_alias_not_filesystem_path() -> None:
    source = StorageSourceRegistration(
        "archive-1", "org-1", "storage-service-1", "Scientific archive", "primary-archive"
    )
    assert source.root_alias == "primary-archive"

    with pytest.raises(ValueError):
        StorageSourceRegistration(
            "archive-1", "org-1", "storage-service-1", "Scientific archive", "//nas/share"
        )


def test_catalogue_item_requires_normalized_relative_path() -> None:
    with pytest.raises(ValueError):
        replace(_item(), relative_path="../secret.jpg")
    with pytest.raises(ValueError):
        replace(_item(), relative_path="folder\\image.jpg")


def test_catalogue_batch_digest_detects_tampering_and_supports_chain() -> None:
    batch = StorageCatalogueBatch(
        batch_id="batch-1",
        storage_id="archive-1",
        organization_id="org-1",
        service_id="storage-service-1",
        scan_id="scan-1",
        sequence=1,
        final=False,
        checkpoint="Expedition-A/Camera-1/IMG_0001.jpg",
        items=(_item(),),
    )
    signed = replace(batch, batch_sha256=batch.calculated_sha256())
    assert signed.verify()

    tampered = replace(signed, checkpoint="different")
    assert not tampered.verify()

    second = StorageCatalogueBatch(
        batch_id="batch-2",
        storage_id="archive-1",
        organization_id="org-1",
        service_id="storage-service-1",
        scan_id="scan-1",
        sequence=2,
        final=True,
        checkpoint="",
        items=(),
        previous_batch_sha256=signed.batch_sha256,
    )
    second = replace(second, batch_sha256=second.calculated_sha256())
    assert second.verify()
    assert second.previous_batch_sha256 == signed.batch_sha256


def test_governed_read_contains_decision_digest_and_bounded_range() -> None:
    digest = authorization_digest(
        {"allowed": True, "policy_ids": ["p1"], "contract_id": "c1"}
    )
    request = GovernedStorageRead(
        request_id="read-1",
        storage_id="archive-1",
        object_id="obj-1",
        organization_id="org-1",
        subject_id="researcher-1",
        purpose="research",
        start=100,
        end=999,
        expires_at_epoch=1_900_000_000,
        authorization_sha256=digest,
    )
    assert request.start == 100
    assert request.end == 999
    assert len(request.authorization_sha256) == 64

    with pytest.raises(ValueError):
        replace(request, start=1000, end=999)


def test_visible_directory_preview_priority_is_bounded_and_deduplicated() -> None:
    request = PreviewPriorityRequest(
        request_id="preview-1",
        storage_id="archive-1",
        organization_id="org-1",
        media_ids=("m1", "m2", "m3"),
        priority=100,
        reason="visible-directory",
        requested_by="researcher-1",
    )
    assert request.reason == "visible-directory"

    with pytest.raises(ValueError):
        replace(request, media_ids=("m1", "m1"))
    with pytest.raises(ValueError):
        replace(request, priority=1001)
