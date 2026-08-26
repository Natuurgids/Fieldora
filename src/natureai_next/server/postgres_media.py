"""PostgreSQL metadata repository for governed media and resumable uploads."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from natureai_next.server.media import MediaInstanceRecord, MediaRecord, UploadSession
from natureai_next.server.media_links import PostgresMediaAssociationRepository


class PostgresMediaMetadataRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                # API and worker processes start together on a clean database. PostgreSQL
                # can still race in system-catalog type creation even with IF NOT EXISTS,
                # so serialize the complete media schema bootstrap transaction.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_media_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS governed_media(
                        media_id TEXT PRIMARY KEY,
                        relative_path TEXT NOT NULL UNIQUE,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL CHECK(size_bytes > 0),
                        sha256 TEXT NOT NULL CHECK(length(sha256) = 64)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS governed_media_instances(
                        instance_id TEXT PRIMARY KEY,
                        media_id TEXT NOT NULL REFERENCES governed_media(media_id)
                            ON DELETE CASCADE,
                        organization_id TEXT NOT NULL,
                        storage_kind TEXT NOT NULL
                            CHECK(storage_kind IN ('managed','referenced')),
                        availability TEXT NOT NULL
                            CHECK(availability IN (
                                'available','offline','missing','changed','corrupt',
                                'permission_denied','cloud_placeholder','unverified'
                            )),
                        size_bytes BIGINT NOT NULL CHECK(size_bytes > 0),
                        sha256 TEXT NOT NULL CHECK(length(sha256) = 64)
                    )
                    """
                )
                cursor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_governed_media_managed_instance_pg "
                    "ON governed_media_instances(media_id) WHERE storage_kind='managed'"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_governed_media_instances_scope_pg "
                    "ON governed_media_instances(organization_id,media_id,storage_kind)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS governed_uploads(
                        upload_id TEXT PRIMARY KEY,
                        subject_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        expected_size BIGINT NOT NULL CHECK(expected_size > 0),
                        expected_sha256 TEXT NOT NULL
                            CHECK(length(expected_sha256) = 64),
                        received_bytes BIGINT NOT NULL
                            CHECK(received_bytes >= 0 AND received_bytes <= expected_size)
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_governed_media_scope_pg "
                    "ON governed_media(organization_id,project_id,media_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_governed_media_content_pg "
                    "ON governed_media(organization_id,sha256,size_bytes)"
                )
                cursor.execute(
                    "SELECT media_id,organization_id,size_bytes,sha256 FROM governed_media m "
                    "WHERE NOT EXISTS(SELECT 1 FROM governed_media_instances i "
                    "WHERE i.media_id=m.media_id AND i.storage_kind='managed')"
                )
                for media_id, organization_id, size_bytes, sha256 in cursor.fetchall():
                    cursor.execute(
                        "INSERT INTO governed_media_instances("
                        "instance_id,media_id,organization_id,storage_kind,availability,"
                        "size_bytes,sha256) VALUES(%s,%s,%s,'managed','available',%s,%s)",
                        (
                            str(uuid4()),
                            media_id,
                            organization_id,
                            size_bytes,
                            sha256,
                        ),
                    )
                PostgresMediaAssociationRepository.bootstrap_schema(cursor)
        self.associations = PostgresMediaAssociationRepository(connect, initialize=False)

    def insert_media(self, record: MediaRecord) -> MediaRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._lock_content_identity(cursor, record)
                existing = self._find_content(cursor, record)
                if existing is not None:
                    self._ensure_managed_instance(cursor, existing)
                    return existing
                self._insert_media(cursor, record)
                self._ensure_managed_instance(cursor, record)
        return record

    def insert_upload(self, upload: UploadSession) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO governed_uploads("
                    "upload_id,subject_id,organization_id,project_id,filename,mime_type,"
                    "expected_size,expected_sha256,received_bytes"
                    ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        upload.upload_id,
                        upload.subject_id,
                        upload.organization_id,
                        upload.project_id,
                        upload.filename,
                        upload.mime_type,
                        upload.expected_size,
                        upload.expected_sha256,
                        upload.received_bytes,
                    ),
                )

    def upload(self, upload_id: str) -> UploadSession | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT upload_id,subject_id,organization_id,project_id,filename,"
                    "mime_type,expected_size,expected_sha256,received_bytes "
                    "FROM governed_uploads WHERE upload_id=%s",
                    (upload_id,),
                )
                row = cursor.fetchone()
        return None if row is None else UploadSession(*row)

    def update_upload_offset(
        self, upload_id: str, expected_offset: int, offset: int
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE governed_uploads SET received_bytes=%s "
                    "WHERE upload_id=%s AND received_bytes=%s",
                    (offset, upload_id, expected_offset),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("resumable upload offset update was rejected")

    def delete_upload(self, upload_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM governed_uploads WHERE upload_id=%s", (upload_id,)
                )

    def complete_upload(self, upload_id: str, record: MediaRecord) -> MediaRecord:
        """Commit one verified upload, returning the canonical content record.

        Completion is idempotent for byte-identical content in the same organization.
        The transaction-scoped advisory lock closes the race where two web requests
        finish the same content concurrently without requiring a destructive uniqueness
        migration over pre-existing deployments.
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT received_bytes,expected_size FROM governed_uploads "
                    "WHERE upload_id=%s FOR UPDATE",
                    (upload_id,),
                )
                row = cursor.fetchone()
                if row is None or int(row[0]) != int(row[1]):
                    raise RuntimeError("resumable upload is not complete")
                self._lock_content_identity(cursor, record)
                canonical = self._find_content(cursor, record)
                if canonical is None:
                    self._insert_media(cursor, record)
                    canonical = record
                self._ensure_managed_instance(cursor, canonical)
                cursor.execute(
                    "DELETE FROM governed_uploads WHERE upload_id=%s", (upload_id,)
                )
        return canonical

    def record(self, media_id: str) -> MediaRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,relative_path,organization_id,project_id,mime_type,"
                    "size_bytes,sha256 FROM governed_media WHERE media_id=%s",
                    (media_id,),
                )
                row = cursor.fetchone()
        return None if row is None else MediaRecord(*row)

    def records(
        self, organization_id: str, project_id: str = "", limit: int = 200
    ) -> tuple[MediaRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if project_id:
                    cursor.execute(
                        "SELECT media_id,relative_path,organization_id,project_id,"
                        "mime_type,size_bytes,sha256 FROM governed_media "
                        "WHERE organization_id=%s AND project_id=%s "
                        "ORDER BY media_id DESC LIMIT %s",
                        (organization_id, project_id, limit),
                    )
                else:
                    cursor.execute(
                        "SELECT media_id,relative_path,organization_id,project_id,"
                        "mime_type,size_bytes,sha256 FROM governed_media "
                        "WHERE organization_id=%s ORDER BY media_id DESC LIMIT %s",
                        (organization_id, limit),
                    )
                rows = cursor.fetchall()
        return tuple(MediaRecord(*row) for row in rows)

    def instances(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaInstanceRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT instance_id,media_id,organization_id,storage_kind,availability,"
                    "size_bytes,sha256 FROM governed_media_instances "
                    "WHERE media_id=%s AND organization_id=%s "
                    "ORDER BY storage_kind,instance_id",
                    (media_id, organization_id),
                )
                rows = cursor.fetchall()
        return tuple(MediaInstanceRecord(*row) for row in rows)

    @staticmethod
    def _lock_content_identity(cursor: Any, record: MediaRecord) -> None:
        raw_key = "\x1f".join(
            (
                record.organization_id,
                record.sha256,
                str(record.size_bytes),
            )
        ).encode("utf-8")
        key = hashlib.sha256(raw_key).hexdigest()
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))

    @staticmethod
    def _find_content(cursor: Any, record: MediaRecord) -> MediaRecord | None:
        cursor.execute(
            "SELECT media_id,relative_path,organization_id,project_id,mime_type,"
            "size_bytes,sha256 FROM governed_media "
            "WHERE organization_id=%s AND sha256=%s AND size_bytes=%s "
            "ORDER BY media_id LIMIT 1",
            (
                record.organization_id,
                record.sha256,
                record.size_bytes,
            ),
        )
        row = cursor.fetchone()
        return None if row is None else MediaRecord(*row)

    @staticmethod
    def _insert_media(cursor: Any, record: MediaRecord) -> None:
        cursor.execute(
            "INSERT INTO governed_media("
            "media_id,relative_path,organization_id,project_id,mime_type,size_bytes,sha256"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                record.media_id,
                record.relative_path,
                record.organization_id,
                record.project_id,
                record.mime_type,
                record.size_bytes,
                record.sha256,
            ),
        )

    @staticmethod
    def _ensure_managed_instance(cursor: Any, record: MediaRecord) -> None:
        cursor.execute(
            "INSERT INTO governed_media_instances("
            "instance_id,media_id,organization_id,storage_kind,availability,size_bytes,sha256"
            ") VALUES(%s,%s,%s,'managed','available',%s,%s) "
            "ON CONFLICT (media_id) WHERE storage_kind='managed' DO NOTHING",
            (
                str(uuid4()),
                record.media_id,
                record.organization_id,
                record.size_bytes,
                record.sha256,
            ),
        )
