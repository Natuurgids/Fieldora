"""Isolated governed-media registry and contained file store."""

from __future__ import annotations

import hashlib
import mimetypes
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from natureai_next.server.media_links import (
    MediaAssociationRepository,
    SqliteMediaAssociationRepository,
)
from natureai_next.server.object_storage import FileObjectStore, ObjectStore

_INSTANCE_AVAILABILITY = {
    "available",
    "offline",
    "missing",
    "changed",
    "corrupt",
    "permission_denied",
    "cloud_placeholder",
    "unverified",
}


@dataclass(frozen=True, slots=True)
class MediaRecord:
    media_id: str
    relative_path: str | None
    organization_id: str
    project_id: str
    mime_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class MediaInstanceRecord:
    instance_id: str
    media_id: str
    organization_id: str
    storage_kind: str
    availability: str
    size_bytes: int
    sha256: str
    source_ref: str = ""


@dataclass(frozen=True, slots=True)
class UploadSession:
    upload_id: str
    subject_id: str
    organization_id: str
    project_id: str
    filename: str
    mime_type: str
    expected_size: int
    expected_sha256: str
    received_bytes: int


class MediaMetadataRepository(Protocol):
    def insert_media(self, record: MediaRecord) -> MediaRecord | None: ...
    def insert_upload(self, upload: UploadSession) -> None: ...
    def upload(self, upload_id: str) -> UploadSession | None: ...
    def update_upload_offset(
        self, upload_id: str, expected_offset: int, offset: int
    ) -> None: ...
    def delete_upload(self, upload_id: str) -> None: ...
    def complete_upload(
        self, upload_id: str, record: MediaRecord
    ) -> MediaRecord | None: ...
    def attach_referenced(
        self,
        *,
        organization_id: str,
        project_id: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        source_ref: str,
        availability: str = "available",
    ) -> MediaRecord: ...
    def record(self, media_id: str) -> MediaRecord | None: ...
    def records(
        self, organization_id: str, project_id: str = "", limit: int = 200
    ) -> tuple[MediaRecord, ...]: ...
    def instances(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaInstanceRecord, ...]: ...


class GovernedMediaStore:
    def __init__(
        self,
        database_path: Path,
        storage_root: Path,
        object_store: ObjectStore | None = None,
        metadata: MediaMetadataRepository | None = None,
    ) -> None:
        self._database_path = database_path
        self._storage_root = storage_root.resolve()
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._objects = object_store or FileObjectStore(self._storage_root)
        self._metadata = metadata
        database_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_associations = (
            None if metadata is None else getattr(metadata, "associations", None)
        )
        self._associations: MediaAssociationRepository = (
            SqliteMediaAssociationRepository(database_path)
            if metadata_associations is None
            else metadata_associations
        )
        if metadata is not None:
            return
        connection = sqlite3.connect(database_path)
        try:
            self._bootstrap_sqlite_schema(connection)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _bootstrap_sqlite_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS governed_media("
            "media_id TEXT PRIMARY KEY,relative_path TEXT UNIQUE,"
            "organization_id TEXT NOT NULL,project_id TEXT NOT NULL,"
            "mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL)"
        )
        columns = connection.execute("PRAGMA table_info(governed_media)").fetchall()
        relative_column = next((row for row in columns if row[1] == "relative_path"), None)
        if relative_column is not None and int(relative_column[3]) == 1:
            instance_table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='governed_media_instances'"
            ).fetchone()
            preserved_instances: list[tuple[object, ...]] = []
            if instance_table_exists is not None:
                instance_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(governed_media_instances)"
                    ).fetchall()
                }
                source_expression = "source_ref" if "source_ref" in instance_columns else "''"
                preserved_instances = connection.execute(
                    "SELECT instance_id,media_id,organization_id,storage_kind,availability,"
                    f"size_bytes,sha256,{source_expression} FROM governed_media_instances"
                ).fetchall()
                # Drop the child before rebuilding the parent. With foreign keys enabled,
                # dropping governed_media first would cascade-delete existing instances.
                connection.execute("DROP TABLE governed_media_instances")
            connection.execute(
                "CREATE TABLE governed_media_nullable("
                "media_id TEXT PRIMARY KEY,relative_path TEXT UNIQUE,"
                "organization_id TEXT NOT NULL,project_id TEXT NOT NULL,"
                "mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO governed_media_nullable SELECT * FROM governed_media"
            )
            connection.execute("DROP TABLE governed_media")
            connection.execute("ALTER TABLE governed_media_nullable RENAME TO governed_media")
            if preserved_instances:
                connection.execute(
                    "CREATE TABLE governed_media_instances("
                    "instance_id TEXT PRIMARY KEY,media_id TEXT NOT NULL,"
                    "organization_id TEXT NOT NULL,storage_kind TEXT NOT NULL,"
                    "availability TEXT NOT NULL,size_bytes INTEGER NOT NULL,"
                    "sha256 TEXT NOT NULL,source_ref TEXT NOT NULL DEFAULT '',"
                    "FOREIGN KEY(media_id) REFERENCES governed_media(media_id) ON DELETE CASCADE)"
                )
                connection.executemany(
                    "INSERT INTO governed_media_instances("
                    "instance_id,media_id,organization_id,storage_kind,availability,"
                    "size_bytes,sha256,source_ref) VALUES(?,?,?,?,?,?,?,?)",
                    preserved_instances,
                )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS governed_media_instances("
            "instance_id TEXT PRIMARY KEY,media_id TEXT NOT NULL,"
            "organization_id TEXT NOT NULL,storage_kind TEXT NOT NULL,"
            "availability TEXT NOT NULL,size_bytes INTEGER NOT NULL,"
            "sha256 TEXT NOT NULL,source_ref TEXT NOT NULL DEFAULT '',"
            "FOREIGN KEY(media_id) REFERENCES governed_media(media_id) ON DELETE CASCADE)"
        )
        instance_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(governed_media_instances)"
            ).fetchall()
        }
        if "source_ref" not in instance_columns:
            connection.execute(
                "ALTER TABLE governed_media_instances "
                "ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_governed_media_managed_instance "
            "ON governed_media_instances(media_id) WHERE storage_kind='managed'"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_governed_media_referenced_source "
            "ON governed_media_instances(organization_id,source_ref) "
            "WHERE storage_kind='referenced' AND source_ref<>''"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_governed_media_instances_scope "
            "ON governed_media_instances(organization_id,media_id,storage_kind)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS governed_uploads("
            "upload_id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,"
            "organization_id TEXT NOT NULL,project_id TEXT NOT NULL,"
            "filename TEXT NOT NULL,mime_type TEXT NOT NULL,"
            "expected_size INTEGER NOT NULL,expected_sha256 TEXT NOT NULL,"
            "received_bytes INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_governed_media_content "
            "ON governed_media(organization_id,sha256,size_bytes)"
        )
        missing_instances = connection.execute(
            "SELECT media_id,organization_id,size_bytes,sha256 FROM governed_media "
            "WHERE relative_path IS NOT NULL AND NOT EXISTS("
            "SELECT 1 FROM governed_media_instances i "
            "WHERE i.media_id=governed_media.media_id AND i.storage_kind='managed')"
        ).fetchall()
        connection.executemany(
            "INSERT INTO governed_media_instances("
            "instance_id,media_id,organization_id,storage_kind,availability,"
            "size_bytes,sha256,source_ref) "
            "VALUES(?,?,?,'managed','available',?,?,'')",
            [
                (str(uuid4()), media_id, organization_id, size_bytes, sha256)
                for media_id, organization_id, size_bytes, sha256 in missing_instances
            ],
        )

    @property
    def associations(self) -> MediaAssociationRepository:
        return self._associations

    def register(
        self, source: Path, organization_id: str, project_id: str
    ) -> MediaRecord:
        source = source.resolve(strict=True)
        suffix = source.suffix.lower()[:16]
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        size_bytes = source.stat().st_size
        if self._metadata is None:
            existing = self._sqlite_content_record(organization_id, sha256, size_bytes)
            if existing is not None and existing.relative_path is not None:
                return existing
        media_id = str(uuid4())
        relative = f"{media_id[:2]}/{media_id}{suffix}"
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        self._objects.put(relative, source, mime_type, sha256)
        record = MediaRecord(
            media_id,
            relative,
            organization_id,
            project_id,
            mime_type,
            size_bytes,
            sha256,
        )
        try:
            if self._metadata is not None:
                canonical = self._metadata.insert_media(record) or record
                if canonical.relative_path != relative:
                    self._objects.delete(relative)
                return canonical
            canonical = self._sqlite_claim_content(record)
            if canonical.relative_path != relative:
                self._objects.delete(relative)
            return canonical
        except BaseException:
            self._objects.delete(relative)
            raise

    def attach_referenced(
        self,
        *,
        organization_id: str,
        project_id: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        source_ref: str,
        availability: str = "available",
    ) -> MediaRecord:
        digest = _validated_sha256(sha256)
        if size_bytes <= 0:
            raise ValueError("invalid referenced media size")
        source_ref = source_ref.strip()
        if not source_ref:
            raise ValueError("referenced source identity is required")
        if availability not in _INSTANCE_AVAILABILITY:
            raise ValueError("invalid media instance availability")
        if self._metadata is not None:
            return self._metadata.attach_referenced(
                organization_id=organization_id,
                project_id=project_id,
                mime_type=mime_type,
                size_bytes=size_bytes,
                sha256=digest,
                source_ref=source_ref,
                availability=availability,
            )
        connection = sqlite3.connect(self._database_path, timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            source_row = connection.execute(
                "SELECT media_id,size_bytes,sha256 FROM governed_media_instances "
                "WHERE organization_id=? AND storage_kind='referenced' AND source_ref=?",
                (organization_id, source_ref),
            ).fetchone()
            if source_row is not None:
                if int(source_row[1]) != size_bytes or str(source_row[2]) != digest:
                    raise ValueError("referenced source identity changed content")
                row = connection.execute(
                    "SELECT * FROM governed_media WHERE media_id=?", (str(source_row[0]),)
                ).fetchone()
                if row is None:
                    raise RuntimeError("referenced instance lost canonical media")
                connection.commit()
                return MediaRecord(*row)
            row = connection.execute(
                "SELECT * FROM governed_media WHERE organization_id=? "
                "AND sha256=? AND size_bytes=? ORDER BY media_id LIMIT 1",
                (organization_id, digest, size_bytes),
            ).fetchone()
            if row is None:
                canonical = MediaRecord(
                    str(uuid4()),
                    None,
                    organization_id,
                    project_id,
                    mime_type[:200] or "application/octet-stream",
                    size_bytes,
                    digest,
                )
                connection.execute(
                    "INSERT INTO governed_media VALUES(?,?,?,?,?,?,?)",
                    (
                        canonical.media_id,
                        canonical.relative_path,
                        canonical.organization_id,
                        canonical.project_id,
                        canonical.mime_type,
                        canonical.size_bytes,
                        canonical.sha256,
                    ),
                )
            else:
                canonical = MediaRecord(*row)
            connection.execute(
                "INSERT INTO governed_media_instances("
                "instance_id,media_id,organization_id,storage_kind,availability,"
                "size_bytes,sha256,source_ref) "
                "VALUES(?,?,?,'referenced',?,?,?,?)",
                (
                    str(uuid4()),
                    canonical.media_id,
                    organization_id,
                    availability,
                    size_bytes,
                    digest,
                    source_ref,
                ),
            )
            connection.commit()
            return canonical
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_upload(
        self,
        subject_id: str,
        organization_id: str,
        project_id: str,
        filename: str,
        mime_type: str,
        expected_size: int,
        expected_sha256: str,
    ) -> UploadSession:
        if expected_size <= 0 or expected_size > 100 * 1024**3:
            raise ValueError("invalid upload size")
        digest = _validated_sha256(expected_sha256)
        upload = UploadSession(
            str(uuid4()),
            subject_id,
            organization_id,
            project_id,
            Path(filename).name[:255],
            mime_type[:200] or "application/octet-stream",
            expected_size,
            digest,
            0,
        )
        if self._metadata is not None:
            self._metadata.insert_upload(upload)
        else:
            connection = sqlite3.connect(self._database_path)
            try:
                connection.execute(
                    "INSERT INTO governed_uploads VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        upload.upload_id,
                        upload.subject_id,
                        upload.organization_id,
                        upload.project_id,
                        upload.filename,
                        upload.mime_type,
                        upload.expected_size,
                        upload.expected_sha256,
                        0,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        part = self._upload_path(upload.upload_id)
        part.parent.mkdir(parents=True, exist_ok=True)
        part.touch(exist_ok=False)
        return upload

    def upload(self, upload_id: str) -> UploadSession | None:
        if self._metadata is not None:
            return self._metadata.upload(upload_id)
        connection = sqlite3.connect(self._database_path)
        try:
            row = connection.execute(
                "SELECT * FROM governed_uploads WHERE upload_id=?", (upload_id,)
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else UploadSession(*row)

    def append_upload(
        self, upload: UploadSession, start: int, chunk: bytes
    ) -> MediaRecord | UploadSession:
        current = self.upload(upload.upload_id)
        if current is None or current.subject_id != upload.subject_id:
            raise PermissionError("upload unavailable")
        if start != current.received_bytes or not chunk:
            raise ValueError("non-contiguous chunk")
        next_offset = start + len(chunk)
        if next_offset > current.expected_size:
            raise ValueError("chunk exceeds declared size")
        part = self._upload_path(current.upload_id)
        with part.open("r+b") as stream:
            stream.truncate(current.received_bytes)
            stream.seek(current.received_bytes)
            stream.write(chunk)
            stream.flush()
        if self._metadata is not None:
            self._metadata.update_upload_offset(
                current.upload_id, current.received_bytes, next_offset
            )
        else:
            connection = sqlite3.connect(self._database_path)
            try:
                connection.execute(
                    "UPDATE governed_uploads SET received_bytes=? WHERE upload_id=?",
                    (next_offset, current.upload_id),
                )
                connection.commit()
            finally:
                connection.close()
        if next_offset < current.expected_size:
            return UploadSession(
                current.upload_id,
                current.subject_id,
                current.organization_id,
                current.project_id,
                current.filename,
                current.mime_type,
                current.expected_size,
                current.expected_sha256,
                next_offset,
            )
        hasher = hashlib.sha256()
        with part.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        digest = hasher.hexdigest()
        if digest != current.expected_sha256:
            if self._metadata is not None:
                self._metadata.delete_upload(current.upload_id)
            else:
                connection = sqlite3.connect(self._database_path)
                try:
                    connection.execute(
                        "DELETE FROM governed_uploads WHERE upload_id=?",
                        (current.upload_id,),
                    )
                    connection.commit()
                finally:
                    connection.close()
            part.unlink(missing_ok=True)
            raise ValueError("sha256 mismatch")
        if self._metadata is None:
            existing = self._sqlite_content_record(
                current.organization_id,
                digest,
                current.expected_size,
            )
            if existing is not None and existing.relative_path is not None:
                connection = sqlite3.connect(self._database_path)
                try:
                    connection.execute(
                        "DELETE FROM governed_uploads WHERE upload_id=?",
                        (current.upload_id,),
                    )
                    connection.commit()
                finally:
                    connection.close()
                part.unlink(missing_ok=True)
                return existing
        media_id = str(uuid4())
        suffix = Path(current.filename).suffix.lower()[:16]
        relative = f"{media_id[:2]}/{media_id}{suffix}"
        record = MediaRecord(
            media_id,
            relative,
            current.organization_id,
            current.project_id,
            current.mime_type,
            current.expected_size,
            digest,
        )
        self._objects.put(relative, part, record.mime_type, record.sha256)
        try:
            if self._metadata is not None:
                canonical = self._metadata.complete_upload(current.upload_id, record) or record
                if canonical.relative_path != relative:
                    self._objects.delete(relative)
                record = canonical
            else:
                canonical = self._sqlite_claim_content(record, current.upload_id)
                if canonical.relative_path != relative:
                    self._objects.delete(relative)
                record = canonical
        except BaseException:
            self._objects.delete(relative)
            raise
        part.unlink(missing_ok=True)
        return record

    def record(self, media_id: str) -> MediaRecord | None:
        if self._metadata is not None:
            return self._metadata.record(media_id)
        connection = sqlite3.connect(self._database_path)
        try:
            row = connection.execute(
                "SELECT * FROM governed_media WHERE media_id=?", (media_id,)
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else MediaRecord(*row)

    def records(
        self, organization_id: str, project_id: str = "", limit: int = 200
    ) -> tuple[MediaRecord, ...]:
        limit = max(1, min(int(limit), 500))
        if self._metadata is not None:
            return self._metadata.records(organization_id, project_id, limit)
        connection = sqlite3.connect(self._database_path)
        try:
            if project_id:
                rows = connection.execute(
                    "SELECT * FROM governed_media WHERE organization_id=? AND project_id=? "
                    "ORDER BY media_id DESC LIMIT ?",
                    (organization_id, project_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM governed_media WHERE organization_id=? "
                    "ORDER BY media_id DESC LIMIT ?",
                    (organization_id, limit),
                ).fetchall()
        finally:
            connection.close()
        return tuple(MediaRecord(*row) for row in rows)

    def instances(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaInstanceRecord, ...]:
        if self._metadata is not None:
            return self._metadata.instances(media_id, organization_id)
        connection = sqlite3.connect(self._database_path)
        try:
            rows = connection.execute(
                "SELECT instance_id,media_id,organization_id,storage_kind,availability,"
                "size_bytes,sha256,source_ref FROM governed_media_instances "
                "WHERE media_id=? AND organization_id=? ORDER BY storage_kind,instance_id",
                (media_id, organization_id),
            ).fetchall()
        finally:
            connection.close()
        return tuple(MediaInstanceRecord(*row) for row in rows)

    def read_range(self, record: MediaRecord, start: int, end: int) -> bytes:
        if start < 0 or end < start or end >= record.size_bytes:
            raise ValueError("invalid range")
        if record.relative_path is None:
            raise FileNotFoundError("media has no managed byte instance")
        return self._objects.read_range(record.relative_path, start, end)

    def _sqlite_content_record(
        self, organization_id: str, sha256: str, size_bytes: int
    ) -> MediaRecord | None:
        connection = sqlite3.connect(self._database_path)
        try:
            row = connection.execute(
                "SELECT * FROM governed_media WHERE organization_id=? "
                "AND sha256=? AND size_bytes=? ORDER BY media_id LIMIT 1",
                (organization_id, sha256, size_bytes),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else MediaRecord(*row)

    def _sqlite_claim_content(
        self, record: MediaRecord, upload_id: str | None = None
    ) -> MediaRecord:
        if record.relative_path is None:
            raise ValueError("managed media requires an object-store path")
        connection = sqlite3.connect(self._database_path, timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM governed_media WHERE organization_id=? "
                "AND sha256=? AND size_bytes=? ORDER BY media_id LIMIT 1",
                (record.organization_id, record.sha256, record.size_bytes),
            ).fetchone()
            canonical = record if row is None else MediaRecord(*row)
            if row is None:
                connection.execute(
                    "INSERT INTO governed_media VALUES(?,?,?,?,?,?,?)",
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
            elif canonical.relative_path is None:
                connection.execute(
                    "UPDATE governed_media SET relative_path=? WHERE media_id=?",
                    (record.relative_path, canonical.media_id),
                )
                canonical = MediaRecord(
                    canonical.media_id,
                    record.relative_path,
                    canonical.organization_id,
                    canonical.project_id,
                    canonical.mime_type,
                    canonical.size_bytes,
                    canonical.sha256,
                )
            connection.execute(
                "INSERT OR IGNORE INTO governed_media_instances("
                "instance_id,media_id,organization_id,storage_kind,availability,"
                "size_bytes,sha256,source_ref) "
                "VALUES(?,?,?,'managed','available',?,?,'')",
                (
                    str(uuid4()),
                    canonical.media_id,
                    canonical.organization_id,
                    canonical.size_bytes,
                    canonical.sha256,
                ),
            )
            if upload_id is not None:
                connection.execute(
                    "DELETE FROM governed_uploads WHERE upload_id=?", (upload_id,)
                )
            connection.commit()
            return canonical
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _contained(self, relative: str) -> Path:
        candidate = (self._storage_root / relative).resolve()
        try:
            candidate.relative_to(self._storage_root)
        except ValueError as exc:
            raise ValueError("media path escapes storage root") from exc
        return candidate

    def _upload_path(self, upload_id: str) -> Path:
        return self._contained(f".uploads/{upload_id}.part")


def _validated_sha256(value: str) -> str:
    digest = value.casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("invalid sha256")
    return digest
