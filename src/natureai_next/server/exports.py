"""Contained, expiring storage for governed project export results."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from natureai_next import __version__
from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.infrastructure.subsystems.server_exports import (
    SERVER_EXPORTS_MIGRATIONS,
)
from natureai_next.server.object_storage import FileObjectStore, ObjectStore


@dataclass(frozen=True, slots=True)
class GovernedExport:
    export_id: str
    job_id: str
    subject_id: str
    organization_id: str
    project_id: str
    filename: str
    relative_path: str
    size_bytes: int
    sha256: str
    created_at_utc: str
    expires_at_utc: str
    revoked_at_utc: str
    purged_at_utc: str
    signing_key_id: str
    signature_base64: str


class ExportMetadataRepository(Protocol):
    def insert(self, record: GovernedExport) -> None: ...
    def stored(self, export_id: str) -> GovernedExport | None: ...
    def revoke(self, export_id: str, at_utc: str) -> bool: ...
    def attach_attestation(
        self, export_id: str, key_id: str, signature_base64: str
    ) -> bool: ...
    def claim_expired(
        self, cutoff_utc: str, limit: int = 1000
    ) -> tuple[GovernedExport, ...]: ...
    def mark_purged(self, export_id: str, at_utc: str) -> None: ...


class GovernedExportStore:
    def __init__(
        self,
        database_path: Path,
        payload_root: Path,
        metadata: ExportMetadataRepository | None = None,
        object_store: ObjectStore | None = None,
    ) -> None:
        self._database_path = database_path
        self._payload_root = payload_root.resolve()
        self._lock = threading.RLock()
        self._metadata = metadata
        self._objects = object_store or FileObjectStore(self._payload_root)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._payload_root.mkdir(parents=True, exist_ok=True)
        if metadata is not None:
            return
        connection = sqlite3.connect(database_path)
        try:
            MigrationRunner(SERVER_EXPORTS_MIGRATIONS, __version__).apply(connection)
        finally:
            connection.close()

    def create(
        self,
        job_id: str,
        subject_id: str,
        organization_id: str,
        project_id: str,
        writer,
        *,
        lifetime: timedelta = timedelta(days=7),
        filename: str | None = None,
    ) -> GovernedExport:
        export_id = str(uuid4())
        filename = filename or f"fieldora-project-{project_id}.fieldora-project.zip"
        relative_path = f"{export_id}.zip"
        temporary = self._contained(f"{export_id}.partial")
        try:
            writer(temporary)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            size = temporary.stat().st_size
            self._objects.put(
                relative_path, temporary, "application/zip", digest
            )
            created = datetime.now(UTC)
            record = GovernedExport(
                export_id, job_id, subject_id, organization_id, project_id,
                filename, relative_path, size, digest, created.isoformat(),
                (created + lifetime).isoformat(), "", "", "", "",
            )
            if self._metadata is not None:
                self._metadata.insert(record)
            else:
                connection = sqlite3.connect(self._database_path)
                try:
                    connection.execute(
                        "INSERT INTO governed_exports VALUES("
                        + ",".join("?" for _ in range(15))
                        + ")",
                        (
                            record.export_id, record.job_id, record.subject_id,
                            record.organization_id, record.project_id, record.filename,
                            record.relative_path, record.size_bytes, record.sha256,
                            record.created_at_utc, record.expires_at_utc,
                            "", "", "", "",
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()
            return record
        except BaseException:
            self._objects.delete(relative_path)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, export_id: str) -> GovernedExport | None:
        with self._lock:
            record = self._stored_record(export_id)
            if record is None or not self._active(record):
                return None
            return record

    def read_range(self, record: GovernedExport, start: int, end: int) -> bytes:
        with self._lock:
            current = self._stored_record(record.export_id)
            if current is None or not self._active(current):
                raise FileNotFoundError(record.export_id)
            return self._objects.read_range(current.relative_path, start, end)

    def revoke(self, export_id: str) -> bool:
        with self._lock:
            record = self._stored_record(export_id)
            if record is None or record.revoked_at_utc or record.purged_at_utc:
                return False
            now = datetime.now(UTC).isoformat()
            if self._metadata is not None:
                if not self._metadata.revoke(export_id, now):
                    return False
            else:
                connection = sqlite3.connect(self._database_path)
                try:
                    cursor = connection.execute(
                        "UPDATE governed_exports SET revoked_at_utc=? "
                        "WHERE export_id=? AND revoked_at_utc=''",
                        (now, export_id),
                    )
                    connection.commit()
                    if cursor.rowcount != 1:
                        return False
                finally:
                    connection.close()
            self._objects.delete(record.relative_path)
            self._mark_purged(export_id, now)
            return True

    def attach_attestation(
        self, export_id: str, key_id: str, signature_base64: str
    ) -> GovernedExport:
        with self._lock:
            record = self._stored_record(export_id)
            if record is None or not self._active(record):
                raise FileNotFoundError(export_id)
            if self._metadata is not None:
                if not self._metadata.attach_attestation(
                    export_id, key_id, signature_base64
                ):
                    raise FileExistsError("export already has an attestation")
            else:
                connection = sqlite3.connect(self._database_path)
                try:
                    cursor = connection.execute(
                        "UPDATE governed_exports "
                        "SET signing_key_id=?,signature_base64=? "
                        "WHERE export_id=? AND signing_key_id=''",
                        (key_id, signature_base64, export_id),
                    )
                    connection.commit()
                    if cursor.rowcount != 1:
                        raise FileExistsError(
                            "export already has an attestation"
                        )
                finally:
                    connection.close()
            updated = self._stored_record(export_id)
            if updated is None:
                raise FileNotFoundError(export_id)
            return updated

    @staticmethod
    def attestation(record: GovernedExport) -> dict | None:
        if not record.signing_key_id or not record.signature_base64:
            return None
        return {
            "schema_version": 1,
            "algorithm": "Ed25519",
            "key_id": record.signing_key_id,
            "package_sha256": record.sha256,
            "signature": record.signature_base64,
        }

    def purge_expired(self, at_utc: datetime | None = None) -> int:
        cutoff = at_utc or datetime.now(UTC)
        with self._lock:
            if self._metadata is not None:
                rows = self._metadata.claim_expired(cutoff.isoformat())
                for record in rows:
                    self._objects.delete(record.relative_path)
                return len(rows)
            connection = sqlite3.connect(self._database_path)
            try:
                rows = connection.execute(
                    "SELECT * FROM governed_exports WHERE purged_at_utc='' AND "
                    "(revoked_at_utc<>'' OR expires_at_utc<=?) ORDER BY export_id",
                    (cutoff.isoformat(),),
                ).fetchall()
            finally:
                connection.close()
            for row in rows:
                record = GovernedExport(*row)
                self._objects.delete(record.relative_path)
                self._mark_purged(record.export_id, cutoff.isoformat())
            return len(rows)

    def _stored_record(self, export_id: str) -> GovernedExport | None:
        if self._metadata is not None:
            return self._metadata.stored(export_id)
        connection = sqlite3.connect(self._database_path)
        try:
            row = connection.execute(
                "SELECT * FROM governed_exports WHERE export_id=?", (export_id,)
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else GovernedExport(*row)

    def _active(self, record: GovernedExport) -> bool:
        return (
            not record.revoked_at_utc
            and not record.purged_at_utc
            and datetime.fromisoformat(record.expires_at_utc) > datetime.now(UTC)
        )

    def _mark_purged(self, export_id: str, at_utc: str) -> None:
        if self._metadata is not None:
            self._metadata.mark_purged(export_id, at_utc)
            return
        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute(
                "UPDATE governed_exports SET purged_at_utc=? WHERE export_id=?",
                (at_utc, export_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _contained(self, relative_path: str) -> Path:
        candidate = (self._payload_root / relative_path).resolve()
        if candidate.parent != self._payload_root:
            raise ValueError("export path escapes its payload root")
        return candidate
