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


@dataclass(frozen=True, slots=True)
class MediaRecord:
    media_id: str
    relative_path: str
    organization_id: str
    project_id: str
    mime_type: str
    size_bytes: int
    sha256: str


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
    def record(self, media_id: str) -> MediaRecord | None: ...
    def records(
        self, organization_id: str, project_id: str = "", limit: int = 200
    ) -> tuple[MediaRecord, ...]: ...


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
        metadata_associations = None if metadata is None else getattr(metadata, "associations", None)
        self._associations: MediaAssociationRepository = (
            SqliteMediaAssociationRepository(database_path)
            if metadata_associations is None
            else metadata_associations
        )
        if metadata is not None:
            return
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS governed_media("
                "media_id TEXT PRIMARY KEY,relative_path TEXT NOT NULL UNIQUE,"
                "organization_id TEXT NOT NULL,project_id TEXT NOT NULL,"
                "mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL)"
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
            connection.commit()
        finally:
            connection.close()

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
            existing = self._sqlite_content_record(
                organization_id, sha256, size_bytes
            )
            if existing is not None:
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
                if canonical.media_id != record.media_id:
                    self._objects.delete(relative)
                return canonical
            connection = sqlite3.connect(self._database_path)
            try:
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
                connection.commit()
            finally:
                connection.close()
        except BaseException:
            self._objects.delete(relative)
            raise
        return record

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
        digest = expected_sha256.casefold()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid sha256")
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
            if existing is not None:
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
                if canonical.media_id != record.media_id:
                    self._objects.delete(relative)
                record = canonical
            else:
                connection = sqlite3.connect(self._database_path)
                try:
                    connection.execute("BEGIN")
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
                    connection.execute(
                        "DELETE FROM governed_uploads WHERE upload_id=?",
                        (current.upload_id,),
                    )
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
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

    def read_range(self, record: MediaRecord, start: int, end: int) -> bytes:
        if start < 0 or end < start or end >= record.size_bytes:
            raise ValueError("invalid range")
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

    def _contained(self, relative: str) -> Path:
        candidate = (self._storage_root / relative).resolve()
        try:
            candidate.relative_to(self._storage_root)
        except ValueError as exc:
            raise ValueError("media path escapes storage root") from exc
        return candidate

    def _upload_path(self, upload_id: str) -> Path:
        return self._contained(f".uploads/{upload_id}.part")
