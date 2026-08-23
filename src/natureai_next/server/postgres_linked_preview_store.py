"""Managed thumbnail bytes for linked storage media.

Storage nodes remain outbound-only. A worker may upload a small derivative only while it
owns the corresponding preview lease. The original archive bytes never enter this store.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.storage_exchange import PreviewState

_MAX_PREVIEW_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LinkedPreviewObject:
    media_id: str
    mime_type: str
    sha256: str
    payload: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.payload)


class PostgresLinkedPreviewStore:
    """Persist bounded governed preview derivatives behind an active worker lease."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_linked_preview_store_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_preview_objects_pg(
                        media_id TEXT PRIMARY KEY
                            REFERENCES linked_storage_media_pg(media_id) ON DELETE CASCADE,
                        mime_type TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL CHECK(size_bytes > 0),
                        payload BYTEA NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def put_leased_preview(
        self,
        *,
        media_id: str,
        storage_id: str,
        organization_id: str,
        service_id: str,
        worker_id: str,
        mime_type: str,
        sha256: str,
        payload: bytes,
    ) -> LinkedPreviewObject:
        media_id = media_id.strip()
        storage_id = storage_id.strip()
        organization_id = organization_id.strip()
        service_id = service_id.strip()
        worker_id = worker_id.strip()
        mime_type = mime_type.strip().casefold()
        digest = sha256.strip().casefold()
        if not all((media_id, storage_id, organization_id, service_id, worker_id)):
            raise ValueError("preview upload identity is required")
        if mime_type != "image/jpeg":
            raise ValueError("linked preview upload must be image/jpeg")
        if not 1 <= len(payload) <= _MAX_PREVIEW_BYTES:
            raise ValueError("linked preview upload size is invalid")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("linked preview sha256 is invalid")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("linked preview sha256 mismatch")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT organization_id,service_id FROM linked_storage_sources_pg "
                    "WHERE storage_id=%s AND enabled=TRUE FOR SHARE",
                    (storage_id,),
                )
                source = cursor.fetchone()
                if source is None:
                    raise KeyError(storage_id)
                if str(source[0]) != organization_id or str(source[1]) != service_id:
                    raise PermissionError("storage source identity mismatch")

                cursor.execute(
                    "SELECT q.claimed_by FROM linked_preview_queue_pg q "
                    "JOIN linked_storage_media_pg m ON m.media_id=q.media_id "
                    "WHERE q.media_id=%s AND q.storage_id=%s "
                    "AND m.organization_id=%s AND q.lease_until>NOW() "
                    "FOR UPDATE OF q",
                    (media_id, storage_id, organization_id),
                )
                lease = cursor.fetchone()
                if lease is None or str(lease[0]) != worker_id:
                    raise PermissionError("preview lease is not owned by this worker")

                cursor.execute(
                    "INSERT INTO linked_preview_objects_pg("
                    "media_id,mime_type,sha256,size_bytes,payload,updated_at"
                    ") VALUES(%s,%s,%s,%s,%s,NOW()) "
                    "ON CONFLICT(media_id) DO UPDATE SET "
                    "mime_type=excluded.mime_type,sha256=excluded.sha256,"
                    "size_bytes=excluded.size_bytes,payload=excluded.payload,updated_at=NOW()",
                    (media_id, mime_type, digest, len(payload), payload),
                )
                cursor.execute(
                    "UPDATE linked_storage_media_pg SET thumbnail_state=%s,thumbnail_etag=%s "
                    "WHERE media_id=%s AND storage_id=%s AND organization_id=%s",
                    (PreviewState.READY.value, digest, media_id, storage_id, organization_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(media_id)
                cursor.execute(
                    "DELETE FROM linked_preview_queue_pg WHERE media_id=%s AND storage_id=%s",
                    (media_id, storage_id),
                )
        return LinkedPreviewObject(media_id, mime_type, digest, bytes(payload))

    def preview(self, media_id: str) -> LinkedPreviewObject | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT p.media_id,p.mime_type,p.sha256,p.payload "
                    "FROM linked_preview_objects_pg p "
                    "JOIN linked_storage_media_pg m ON m.media_id=p.media_id "
                    "WHERE p.media_id=%s AND m.thumbnail_state=%s",
                    (media_id.strip(), PreviewState.READY.value),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return LinkedPreviewObject(str(row[0]), str(row[1]), str(row[2]), bytes(row[3]))


class PostgresLinkedStorageBrowserRepository(PostgresLinkedStorageRepository):
    """Catalogue repository with governed preview-byte reads for the browser API."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        super().__init__(connect)
        self._preview_store = PostgresLinkedPreviewStore(connect)

    def preview(self, media_id: str) -> LinkedPreviewObject | None:
        return self._preview_store.preview(media_id)
