"""PostgreSQL catalogue for externally stored, governed scientific media.

Only opaque storage-service identities and relative object paths are persisted here.
The organisation's actual SMB/NFS/object-store mount configuration remains inside the
trusted storage service and is never exposed to browser clients.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageObjectState,
    StorageSourceRegistration,
)


@dataclass(frozen=True, slots=True)
class ServerLinkedMedia:
    media_id: str
    storage_id: str
    object_id: str
    organization_id: str
    relative_path: str
    filename: str
    mime_type: str
    size_bytes: int
    modified_ns: int
    object_state: StorageObjectState
    sha256: str
    thumbnail_state: PreviewState
    thumbnail_etag: str
    project_id: str
    metadata: dict[str, Any]


class PostgresLinkedStorageRepository:
    """Shared multi-server catalogue and interactive preview queue."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_linked_storage_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_storage_sources_pg(
                        storage_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        service_id TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        root_alias TEXT NOT NULL,
                        read_only BOOLEAN NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        UNIQUE(organization_id,root_alias)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_storage_media_pg(
                        media_id TEXT PRIMARY KEY,
                        storage_id TEXT NOT NULL REFERENCES linked_storage_sources_pg(storage_id),
                        object_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL CHECK(size_bytes >= 0),
                        modified_ns BIGINT NOT NULL CHECK(modified_ns >= 0),
                        object_state TEXT NOT NULL,
                        sha256 TEXT NOT NULL DEFAULT '',
                        thumbnail_state TEXT NOT NULL,
                        thumbnail_etag TEXT NOT NULL DEFAULT '',
                        project_id TEXT NOT NULL DEFAULT '',
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        UNIQUE(storage_id,object_id),
                        UNIQUE(storage_id,relative_path)
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_linked_storage_media_scope_pg "
                    "ON linked_storage_media_pg(organization_id,project_id,media_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_linked_storage_media_path_pg "
                    "ON linked_storage_media_pg(storage_id,relative_path)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_storage_scans_pg(
                        storage_id TEXT NOT NULL,
                        scan_id TEXT NOT NULL,
                        service_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        last_sequence INTEGER NOT NULL,
                        last_checkpoint TEXT NOT NULL,
                        last_batch_sha256 TEXT NOT NULL,
                        final BOOLEAN NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY(storage_id,scan_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_preview_queue_pg(
                        media_id TEXT PRIMARY KEY REFERENCES linked_storage_media_pg(media_id),
                        storage_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 1000),
                        reason TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        claimed_by TEXT NOT NULL DEFAULT '',
                        lease_until TIMESTAMPTZ
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_linked_preview_queue_priority_pg "
                    "ON linked_preview_queue_pg(priority DESC,requested_at,media_id)"
                )

    @property
    def connect_factory(self) -> Callable[[], Any]:
        return self._connect

    def register_source(self, source: StorageSourceRegistration) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO linked_storage_sources_pg("
                    "storage_id,organization_id,service_id,display_name,root_alias,read_only"
                    ") VALUES(%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(storage_id) DO UPDATE SET "
                    "display_name=excluded.display_name,root_alias=excluded.root_alias,"
                    "read_only=excluded.read_only "
                    "WHERE linked_storage_sources_pg.organization_id=excluded.organization_id "
                    "AND linked_storage_sources_pg.service_id=excluded.service_id",
                    (
                        source.storage_id,
                        source.organization_id,
                        source.service_id,
                        source.display_name,
                        source.root_alias,
                        source.read_only,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("storage source ownership cannot be changed")

    def source(self, storage_id: str) -> StorageSourceRegistration | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT storage_id,organization_id,service_id,display_name,root_alias,read_only "
                    "FROM linked_storage_sources_pg WHERE storage_id=%s AND enabled=TRUE",
                    (storage_id,),
                )
                row = cursor.fetchone()
        return None if row is None else StorageSourceRegistration(
            str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]), bool(row[5])
        )

    def apply_catalogue_batch(self, batch: StorageCatalogueBatch) -> tuple[int, int]:
        """Apply one hash-chained batch exactly once; return inserted/updated counts."""
        if not batch.verify():
            raise ValueError("catalogue batch digest is invalid")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT service_id,organization_id FROM linked_storage_sources_pg "
                    "WHERE storage_id=%s AND enabled=TRUE FOR SHARE",
                    (batch.storage_id,),
                )
                source = cursor.fetchone()
                if source is None:
                    raise ValueError("linked storage source is unavailable")
                if str(source[0]) != batch.service_id or str(source[1]) != batch.organization_id:
                    raise ValueError("catalogue batch source identity mismatch")

                cursor.execute(
                    "SELECT last_sequence,last_batch_sha256,final FROM linked_storage_scans_pg "
                    "WHERE storage_id=%s AND scan_id=%s FOR UPDATE",
                    (batch.storage_id, batch.scan_id),
                )
                scan = cursor.fetchone()
                if scan is None:
                    if batch.sequence != 1 or batch.previous_batch_sha256:
                        raise ValueError("catalogue scan must begin at sequence 1")
                else:
                    last_sequence = int(scan[0])
                    last_digest = str(scan[1])
                    if last_sequence == batch.sequence and last_digest == batch.batch_sha256:
                        return 0, 0
                    if bool(scan[2]):
                        raise ValueError("catalogue scan is already final")
                    if batch.sequence != last_sequence + 1:
                        raise ValueError("catalogue batch sequence gap")
                    if batch.previous_batch_sha256 != last_digest:
                        raise ValueError("catalogue hash chain mismatch")

                inserted = 0
                updated = 0
                for item in batch.items:
                    cursor.execute(
                        "SELECT media_id FROM linked_storage_media_pg "
                        "WHERE storage_id=%s AND object_id=%s",
                        (batch.storage_id, item.object_id),
                    )
                    existing = cursor.fetchone()
                    media_id = (
                        f"linked:{batch.storage_id}:{item.object_id}"
                        if existing is None
                        else str(existing[0])
                    )
                    cursor.execute(
                        "INSERT INTO linked_storage_media_pg("
                        "media_id,storage_id,object_id,organization_id,relative_path,filename,"
                        "mime_type,size_bytes,modified_ns,object_state,sha256,thumbnail_state,"
                        "thumbnail_etag,project_id,metadata_json"
                        ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
                        "ON CONFLICT(storage_id,object_id) DO UPDATE SET "
                        "relative_path=excluded.relative_path,filename=excluded.filename,"
                        "mime_type=excluded.mime_type,size_bytes=excluded.size_bytes,"
                        "modified_ns=excluded.modified_ns,object_state=excluded.object_state,"
                        "sha256=excluded.sha256,thumbnail_state=excluded.thumbnail_state,"
                        "thumbnail_etag=excluded.thumbnail_etag,project_id=excluded.project_id,"
                        "metadata_json=excluded.metadata_json",
                        (
                            media_id,
                            batch.storage_id,
                            item.object_id,
                            batch.organization_id,
                            item.relative_path,
                            item.filename,
                            item.mime_type,
                            item.size_bytes,
                            item.modified_ns,
                            item.state.value,
                            item.sha256,
                            item.thumbnail_state.value,
                            item.thumbnail_etag,
                            item.project_id,
                            json.dumps(item.metadata, sort_keys=True),
                        ),
                    )
                    if existing is None:
                        inserted += 1
                    else:
                        updated += 1

                cursor.execute(
                    "INSERT INTO linked_storage_scans_pg("
                    "storage_id,scan_id,service_id,organization_id,last_sequence,"
                    "last_checkpoint,last_batch_sha256,final"
                    ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(storage_id,scan_id) DO UPDATE SET "
                    "last_sequence=excluded.last_sequence,last_checkpoint=excluded.last_checkpoint,"
                    "last_batch_sha256=excluded.last_batch_sha256,final=excluded.final,"
                    "updated_at=NOW()",
                    (
                        batch.storage_id,
                        batch.scan_id,
                        batch.service_id,
                        batch.organization_id,
                        batch.sequence,
                        batch.checkpoint,
                        batch.batch_sha256,
                        batch.final,
                    ),
                )
        return inserted, updated

    def media(self, media_id: str) -> ServerLinkedMedia | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,storage_id,object_id,organization_id,relative_path,filename,"
                    "mime_type,size_bytes,modified_ns,object_state,sha256,thumbnail_state,"
                    "thumbnail_etag,project_id,metadata_json FROM linked_storage_media_pg "
                    "WHERE media_id=%s",
                    (media_id,),
                )
                row = cursor.fetchone()
        return None if row is None else _decode_media(row)

    def browse(
        self,
        organization_id: str,
        storage_id: str,
        prefix: str = "",
        limit: int = 200,
    ) -> tuple[ServerLinkedMedia, ...]:
        bounded = max(1, min(int(limit), 1000))
        pattern = "%" if not prefix else f"{prefix.rstrip('/')}/%"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,storage_id,object_id,organization_id,relative_path,filename,"
                    "mime_type,size_bytes,modified_ns,object_state,sha256,thumbnail_state,"
                    "thumbnail_etag,project_id,metadata_json FROM linked_storage_media_pg "
                    "WHERE organization_id=%s AND storage_id=%s AND relative_path LIKE %s "
                    "AND object_state<>%s ORDER BY relative_path LIMIT %s",
                    (
                        organization_id,
                        storage_id,
                        pattern,
                        StorageObjectState.MISSING.value,
                        bounded,
                    ),
                )
                rows = cursor.fetchall()
        return tuple(_decode_media(row) for row in rows)

    def request_preview(
        self,
        *,
        media_id: str,
        organization_id: str,
        priority: int,
        reason: str,
        requested_by: str,
    ) -> bool:
        bounded_priority = max(0, min(int(priority), 1000))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT storage_id,thumbnail_state FROM linked_storage_media_pg "
                    "WHERE media_id=%s AND organization_id=%s",
                    (media_id, organization_id),
                )
                row = cursor.fetchone()
                if row is None or str(row[1]) == PreviewState.READY.value:
                    return False
                cursor.execute(
                    "INSERT INTO linked_preview_queue_pg("
                    "media_id,storage_id,organization_id,priority,reason,requested_by"
                    ") VALUES(%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(media_id) DO UPDATE SET "
                    "priority=GREATEST(linked_preview_queue_pg.priority,excluded.priority),"
                    "reason=excluded.reason,requested_by=excluded.requested_by,"
                    "requested_at=LEAST(linked_preview_queue_pg.requested_at,NOW())",
                    (
                        media_id,
                        str(row[0]),
                        organization_id,
                        bounded_priority,
                        reason[:120],
                        requested_by,
                    ),
                )
        return True

    def preview(self, media_id: str):
        from natureai_next.server.postgres_linked_preview_store import LinkedPreviewObject

        media_id = media_id.strip()
        if not media_id:
            return None
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s)", ("linked_preview_objects_pg",))
                if cursor.fetchone()[0] is None:
                    return None
                cursor.execute(
                    "SELECT p.media_id,p.mime_type,p.sha256,p.payload "
                    "FROM linked_preview_objects_pg p "
                    "JOIN linked_storage_media_pg m ON m.media_id=p.media_id "
                    "WHERE p.media_id=%s AND m.thumbnail_state=%s",
                    (media_id, PreviewState.READY.value),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return LinkedPreviewObject(str(row[0]), str(row[1]), str(row[2]), bytes(row[3]))


def _decode_media(row: Any) -> ServerLinkedMedia:
    metadata = row[14] if isinstance(row[14], dict) else json.loads(str(row[14]))
    return ServerLinkedMedia(
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        int(row[7]),
        int(row[8]),
        StorageObjectState(str(row[9])),
        str(row[10]),
        PreviewState(str(row[11])),
        str(row[12]),
        str(row[13]),
        dict(metadata),
    )
