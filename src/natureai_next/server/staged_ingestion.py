"""Durable quarantine, validation, and bounded staged-ingestion orchestration."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from natureai_next.server.jobs import ServerJobRepository


TERMINAL_FILE_STATES = frozenset({"validated", "rejected", "published", "failed"})
PUBLICATION_POLICIES = frozenset({"progressive", "atomic", "review"})


@dataclass(frozen=True, slots=True)
class StagedSubmission:
    submission_id: str
    subject_id: str
    organization_id: str
    project_id: str
    contract_id: str
    purpose: str
    publication_policy: str
    state: str
    expected_files: int
    received_files: int
    total_bytes: int
    created_at_epoch: int
    updated_at_epoch: int


@dataclass(frozen=True, slots=True)
class StagedFile:
    staged_file_id: str
    submission_id: str
    relative_path: str
    filename: str
    declared_mime_type: str
    detected_mime_type: str
    expected_size: int
    expected_sha256: str
    received_bytes: int
    state: str
    quarantine_path: str
    validation_json: dict[str, object]
    media_id: str


class MalwareScanner(Protocol):
    def scan(self, path: Path) -> tuple[bool, str]: ...


class ClamAvScanner:
    """Fail-closed command adapter for a locally managed ClamAV installation."""

    def __init__(self, executable: str = "clamscan", timeout_seconds: int = 300) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def scan(self, path: Path) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                [self.executable, "--no-summary", "--", str(path)],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"scanner_unavailable:{type(exc).__name__}"
        detail = (completed.stdout or completed.stderr).strip()[:1000]
        if completed.returncode == 0:
            return True, detail or "clean"
        if completed.returncode == 1:
            return False, detail or "malware_detected"
        return False, detail or f"scanner_error:{completed.returncode}"


class StagedIngestionStore:
    """SQLite reference store; PostgreSQL may implement the same state contract."""

    def __init__(self, database_path: Path, quarantine_root: Path) -> None:
        self.database_path = database_path
        self.quarantine_root = quarantine_root.resolve()
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS staged_submissions(
                    submission_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    publication_policy TEXT NOT NULL,
                    state TEXT NOT NULL,
                    expected_files INTEGER NOT NULL,
                    received_files INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at_epoch INTEGER NOT NULL,
                    updated_at_epoch INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS staged_files(
                    staged_file_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL REFERENCES staged_submissions(submission_id),
                    relative_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    declared_mime_type TEXT NOT NULL,
                    detected_mime_type TEXT NOT NULL DEFAULT '',
                    expected_size INTEGER NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    received_bytes INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    quarantine_path TEXT NOT NULL UNIQUE,
                    validation_json TEXT NOT NULL DEFAULT '{}',
                    media_id TEXT NOT NULL DEFAULT '',
                    created_at_epoch INTEGER NOT NULL,
                    updated_at_epoch INTEGER NOT NULL,
                    UNIQUE(submission_id,relative_path)
                );
                CREATE INDEX IF NOT EXISTS ix_staged_files_submission_state
                    ON staged_files(submission_id,state,staged_file_id);
                CREATE TABLE IF NOT EXISTS staged_ingestion_events(
                    event_id INTEGER PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    staged_file_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at_epoch INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def create_submission(
        self,
        *,
        subject_id: str,
        organization_id: str,
        project_id: str,
        contract_id: str,
        purpose: str,
        publication_policy: str,
        expected_files: int,
    ) -> StagedSubmission:
        if publication_policy not in PUBLICATION_POLICIES:
            raise ValueError("invalid publication policy")
        if not 1 <= expected_files <= 1_000_000:
            raise ValueError("expected_files must be between 1 and 1000000")
        if not all(value.strip() for value in (subject_id, organization_id, project_id, purpose)):
            raise ValueError("submission ownership and purpose are required")
        now = int(time.time())
        submission_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO staged_submissions VALUES(?,?,?,?,?,?,?,?,?,0,0,?,?)",
                (
                    submission_id,
                    subject_id,
                    organization_id,
                    project_id,
                    contract_id.strip(),
                    purpose.strip(),
                    publication_policy,
                    "uploading",
                    expected_files,
                    now,
                    now,
                ),
            )
            self._event(connection, submission_id, "", "submission_created", {})
        result = self.submission(submission_id)
        assert result is not None
        return result

    def begin_file(
        self,
        submission_id: str,
        *,
        relative_path: str,
        filename: str,
        mime_type: str,
        expected_size: int,
        expected_sha256: str,
    ) -> StagedFile:
        safe_relative = self._safe_relative_path(relative_path or filename)
        digest = expected_sha256.casefold()
        if expected_size <= 0 or expected_size > 100 * 1024**3:
            raise ValueError("invalid staged file size")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid sha256")
        staged_file_id = str(uuid4())
        path = self._quarantine_path(submission_id, staged_file_id)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            submission = connection.execute(
                "SELECT state,expected_files,received_files FROM staged_submissions "
                "WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
            if submission is None or submission["state"] != "uploading":
                raise ValueError("submission is not accepting files")
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM staged_files WHERE submission_id=?",
                    (submission_id,),
                ).fetchone()[0]
            )
            if count >= int(submission["expected_files"]):
                raise ValueError("submission file limit reached")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=False)
            try:
                connection.execute(
                    """
                    INSERT INTO staged_files(
                        staged_file_id,submission_id,relative_path,filename,
                        declared_mime_type,expected_size,expected_sha256,received_bytes,
                        state,quarantine_path,created_at_epoch,updated_at_epoch
                    ) VALUES(?,?,?,?,?,?,?,0,'uploading',?,?,?)
                    """,
                    (
                        staged_file_id,
                        submission_id,
                        safe_relative,
                        Path(filename).name[:255],
                        mime_type[:200] or "application/octet-stream",
                        expected_size,
                        digest,
                        str(path),
                        now,
                        now,
                    ),
                )
                self._event(connection, submission_id, staged_file_id, "file_started", {})
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        result = self.file(staged_file_id)
        assert result is not None
        return result

    def append(self, staged_file_id: str, start: int, chunk: bytes) -> StagedFile:
        if not chunk or len(chunk) > 8 * 1024 * 1024:
            raise ValueError("invalid upload chunk")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM staged_files WHERE staged_file_id=?", (staged_file_id,)
            ).fetchone()
            if row is None or row["state"] != "uploading":
                raise ValueError("staged file is not uploading")
            if start != int(row["received_bytes"]):
                raise ValueError("non-contiguous upload")
            next_offset = start + len(chunk)
            if next_offset > int(row["expected_size"]):
                raise ValueError("upload exceeds declared size")
            path = Path(str(row["quarantine_path"]))
            with path.open("r+b") as stream:
                stream.seek(start)
                stream.write(chunk)
                stream.flush()
            state = "uploaded" if next_offset == int(row["expected_size"]) else "uploading"
            connection.execute(
                "UPDATE staged_files SET received_bytes=?,state=?,updated_at_epoch=? "
                "WHERE staged_file_id=? AND received_bytes=?",
                (next_offset, state, int(time.time()), staged_file_id, start),
            )
            if state == "uploaded":
                connection.execute(
                    "UPDATE staged_submissions SET received_files=received_files+1,"
                    "total_bytes=total_bytes+?,updated_at_epoch=? WHERE submission_id=?",
                    (next_offset, int(time.time()), str(row["submission_id"])),
                )
                self._event(
                    connection,
                    str(row["submission_id"]),
                    staged_file_id,
                    "file_uploaded",
                    {"size": next_offset},
                )
        result = self.file(staged_file_id)
        assert result is not None
        return result

    def seal(self, submission_id: str) -> StagedSubmission:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM staged_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
            if row is None or row["state"] != "uploading":
                raise ValueError("submission cannot be sealed")
            if int(row["received_files"]) != int(row["expected_files"]):
                raise ValueError("submission is incomplete")
            connection.execute(
                "UPDATE staged_submissions SET state='scanning',updated_at_epoch=? "
                "WHERE submission_id=?",
                (int(time.time()), submission_id),
            )
            self._event(connection, submission_id, "", "submission_sealed", {})
        result = self.submission(submission_id)
        assert result is not None
        return result

    def submission(self, submission_id: str) -> StagedSubmission | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM staged_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
        return None if row is None else StagedSubmission(*row)

    def file(self, staged_file_id: str) -> StagedFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT staged_file_id,submission_id,relative_path,filename,"
                "declared_mime_type,detected_mime_type,expected_size,expected_sha256,"
                "received_bytes,state,quarantine_path,validation_json,media_id "
                "FROM staged_files WHERE staged_file_id=?",
                (staged_file_id,),
            ).fetchone()
        if row is None:
            return None
        values = list(row)
        values[11] = json.loads(values[11])
        return StagedFile(*values)

    def files(self, submission_id: str, state: str | None = None) -> tuple[StagedFile, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT staged_file_id FROM staged_files WHERE submission_id=? "
                + ("AND state=? " if state else "")
                + "ORDER BY staged_file_id",
                (submission_id, state) if state else (submission_id,),
            ).fetchall()
        return tuple(item for row in rows if (item := self.file(str(row[0]))) is not None)

    def record_validation(
        self,
        staged_file_id: str,
        *,
        accepted: bool,
        detected_mime_type: str,
        evidence: dict[str, object],
    ) -> None:
        state = "validated" if accepted else "rejected"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT submission_id,state FROM staged_files WHERE staged_file_id=?",
                (staged_file_id,),
            ).fetchone()
            if row is None or row["state"] not in {"uploaded", "validating"}:
                raise ValueError("staged file cannot be validated")
            connection.execute(
                "UPDATE staged_files SET state=?,detected_mime_type=?,validation_json=?,"
                "updated_at_epoch=? WHERE staged_file_id=?",
                (
                    state,
                    detected_mime_type[:200],
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                    int(time.time()),
                    staged_file_id,
                ),
            )
            self._event(
                connection,
                str(row["submission_id"]),
                staged_file_id,
                "file_validated" if accepted else "file_rejected",
                evidence,
            )
            self._refresh_submission_state(connection, str(row["submission_id"]))

    def mark_processing(self, staged_file_ids: tuple[str, ...]) -> None:
        if not staged_file_ids:
            return
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in staged_file_ids)
            cursor = connection.execute(
                f"UPDATE staged_files SET state='processing',updated_at_epoch=? "
                f"WHERE state='validated' AND staged_file_id IN ({placeholders})",
                (int(time.time()), *staged_file_ids),
            )
            if cursor.rowcount != len(staged_file_ids):
                raise ValueError("processing batch contains unavailable files")

    def mark_processed(self, staged_file_ids: tuple[str, ...]) -> None:
        if not staged_file_ids:
            return
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in staged_file_ids)
            connection.execute(
                f"UPDATE staged_files SET state='processed',updated_at_epoch=? "
                f"WHERE state='processing' AND staged_file_id IN ({placeholders})",
                (int(time.time()), *staged_file_ids),
            )
            submission_id = connection.execute(
                "SELECT submission_id FROM staged_files WHERE staged_file_id=?",
                (staged_file_ids[0],),
            ).fetchone()[0]
            self._refresh_submission_state(connection, str(submission_id))

    def mark_published(self, staged_file_id: str, media_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE staged_files SET state='published',media_id=?,updated_at_epoch=? "
                "WHERE staged_file_id=? AND state='processed'",
                (media_id, int(time.time()), staged_file_id),
            )
            row = connection.execute(
                "SELECT submission_id FROM staged_files WHERE staged_file_id=?",
                (staged_file_id,),
            ).fetchone()
            if row is not None:
                self._refresh_submission_state(connection, str(row[0]))

    def set_submission_state(self, submission_id: str, state: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE staged_submissions SET state=?,updated_at_epoch=? "
                "WHERE submission_id=?",
                (state, int(time.time()), submission_id),
            )
            self._event(connection, submission_id, "", f"submission_{state}", {})

    def _refresh_submission_state(
        self, connection: sqlite3.Connection, submission_id: str
    ) -> None:
        counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT state,COUNT(*) FROM staged_files WHERE submission_id=? GROUP BY state",
                (submission_id,),
            )
        }
        total = sum(counts.values())
        state = None
        if total and counts.get("published", 0) == total:
            state = "published"
        elif total and counts.get("processed", 0) + counts.get("rejected", 0) == total:
            state = "ready_to_publish"
        elif total and counts.get("validated", 0) + counts.get("rejected", 0) == total:
            state = "validated" if not counts.get("rejected") else "validated_with_rejections"
        if state:
            connection.execute(
                "UPDATE staged_submissions SET state=?,updated_at_epoch=? "
                "WHERE submission_id=?",
                (state, int(time.time()), submission_id),
            )

    def _quarantine_path(self, submission_id: str, staged_file_id: str) -> Path:
        candidate = (self.quarantine_root / submission_id / f"{staged_file_id}.part").resolve()
        candidate.relative_to(self.quarantine_root)
        return candidate

    @staticmethod
    def _safe_relative_path(value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        parts = tuple(part for part in normalized.split("/") if part)
        if not parts or any(part in {".", ".."} for part in parts):
            raise ValueError("invalid relative path")
        return "/".join(parts)[:2000]

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        submission_id: str,
        staged_file_id: str,
        event_type: str,
        detail: dict[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO staged_ingestion_events("
            "submission_id,staged_file_id,event_type,detail_json,created_at_epoch"
            ") VALUES(?,?,?,?,?)",
            (
                submission_id,
                staged_file_id,
                event_type,
                json.dumps(detail, sort_keys=True, separators=(",", ":")),
                int(time.time()),
            ),
        )


class StagedIngestionService:
    def __init__(
        self,
        store: StagedIngestionStore,
        jobs: ServerJobRepository,
        *,
        malware_scanner: MalwareScanner,
        import_batch_size: int = 250,
        max_archive_members: int = 100_000,
        max_archive_expanded_bytes: int = 100 * 1024**3,
    ) -> None:
        if not 1 <= import_batch_size <= 1000:
            raise ValueError("import_batch_size must be between 1 and 1000")
        self.store = store
        self.jobs = jobs
        self.malware_scanner = malware_scanner
        self.import_batch_size = import_batch_size
        self.max_archive_members = max_archive_members
        self.max_archive_expanded_bytes = max_archive_expanded_bytes

    def seal_and_queue(self, submission_id: str) -> StagedSubmission:
        submission = self.store.seal(submission_id)
        for item in self.store.files(submission_id, "uploaded"):
            self.jobs.enqueue(
                "staged.validate",
                submission.subject_id,
                submission.organization_id,
                submission.project_id,
                {"submission_id": submission_id, "staged_file_id": item.staged_file_id},
            )
        return submission

    def validate_file(self, staged_file_id: str) -> dict[str, object]:
        item = self.store.file(staged_file_id)
        if item is None or item.state != "uploaded":
            raise ValueError("staged file is unavailable for validation")
        path = Path(item.quarantine_path)
        evidence: dict[str, object] = {
            "expected_size": item.expected_size,
            "expected_sha256": item.expected_sha256,
        }
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        actual_sha256 = digest.hexdigest()
        evidence["actual_sha256"] = actual_sha256
        evidence["size_valid"] = path.stat().st_size == item.expected_size
        evidence["checksum_valid"] = actual_sha256 == item.expected_sha256
        detected = self._detect_mime(path, item.filename)
        evidence["declared_mime_type"] = item.declared_mime_type
        evidence["detected_mime_type"] = detected
        evidence["mime_consistent"] = (
            item.declared_mime_type in {"", "application/octet-stream", detected}
        )
        archive_safe, archive_detail = self._archive_safety(path)
        evidence["archive_safe"] = archive_safe
        if archive_detail:
            evidence["archive_detail"] = archive_detail
        malware_clean, malware_detail = self.malware_scanner.scan(path)
        evidence["malware_clean"] = malware_clean
        evidence["malware_detail"] = malware_detail
        accepted = all(
            bool(evidence[key])
            for key in ("size_valid", "checksum_valid", "mime_consistent", "archive_safe", "malware_clean")
        )
        self.store.record_validation(
            staged_file_id,
            accepted=accepted,
            detected_mime_type=detected,
            evidence=evidence,
        )
        return {"accepted": accepted, **evidence}

    def queue_processing(self, submission_id: str) -> tuple[str, ...]:
        submission = self.store.submission(submission_id)
        if submission is None or submission.state not in {
            "validated",
            "validated_with_rejections",
        }:
            raise ValueError("submission is not validated")
        files = self.store.files(submission_id, "validated")
        if not files:
            self.store.set_submission_state(submission_id, "ready_to_publish")
            return ()
        job_ids: list[str] = []
        for offset in range(0, len(files), self.import_batch_size):
            batch = files[offset : offset + self.import_batch_size]
            job = self.jobs.enqueue(
                "staged.process",
                submission.subject_id,
                submission.organization_id,
                submission.project_id,
                {
                    "submission_id": submission_id,
                    "staged_file_ids": [item.staged_file_id for item in batch],
                    "contract_id": submission.contract_id,
                    "purpose": submission.purpose,
                    "publication_policy": submission.publication_policy,
                },
            )
            job_ids.append(job.job_id)
        self.store.set_submission_state(submission_id, "processing")
        return tuple(job_ids)

    def process_batch(self, staged_file_ids: tuple[str, ...]) -> dict[str, object]:
        self.store.mark_processing(staged_file_ids)
        # Media-specific extraction is deliberately downstream of quarantine.
        # This durable boundary is where photo/audio/video/document workers fan out.
        self.store.mark_processed(staged_file_ids)
        return {"processed": len(staged_file_ids)}

    def _archive_safety(self, path: Path) -> tuple[bool, str]:
        if not zipfile.is_zipfile(path):
            return True, ""
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > self.max_archive_members:
                    return False, "archive_member_limit"
                expanded = 0
                for info in infos:
                    normalized = info.filename.replace("\\", "/")
                    parts = tuple(part for part in normalized.split("/") if part)
                    if normalized.startswith("/") or ".." in parts:
                        return False, "unsafe_archive_path"
                    expanded += max(0, info.file_size)
                    if expanded > self.max_archive_expanded_bytes:
                        return False, "archive_expansion_limit"
        except (OSError, zipfile.BadZipFile):
            return False, "invalid_archive"
        return True, ""

    @staticmethod
    def _detect_mime(path: Path, filename: str) -> str:
        with path.open("rb") as stream:
            head = stream.read(32)
        signatures = (
            (b"\xff\xd8\xff", "image/jpeg"),
            (b"\x89PNG\r\n\x1a\n", "image/png"),
            (b"GIF87a", "image/gif"),
            (b"GIF89a", "image/gif"),
            (b"%PDF-", "application/pdf"),
            (b"PK\x03\x04", "application/zip"),
            (b"fLaC", "audio/flac"),
            (b"OggS", "application/ogg"),
        )
        for signature, mime_type in signatures:
            if head.startswith(signature):
                return mime_type
        if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
            return "audio/wav"
        if len(head) >= 12 and head[4:8] == b"ftyp":
            return "video/mp4"
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"
