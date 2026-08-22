"""Durable fenced server job queue with leases and bounded retries."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from natureai_next import __version__
from natureai_next.application.science import (
    ScienceSession,
    ScienceSnapshotRepository,
    default_science_snapshot,
)
from natureai_next.application.science_packages import PortableProjectService
from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.infrastructure.database.science import SqliteScienceRepository
from natureai_next.infrastructure.subsystems.server_jobs import SERVER_JOBS_MIGRATIONS
from natureai_next.server.export_encryption import encrypt_project_export
from natureai_next.server.export_signing import ExportSigningIdentity
from natureai_next.server.exports import GovernedExportStore
from natureai_next.server.search import ScienceRecordSource, SearchProjection


@dataclass(frozen=True, slots=True)
class ServerJob:
    job_id: str
    job_type: str
    subject_id: str
    organization_id: str
    project_id: str
    status: str
    payload: dict
    result: dict
    attempts: int
    lease_until_utc: str
    created_at_utc: str
    updated_at_utc: str
    lease_owner: str
    lease_token: str


class ServerJobRepository(Protocol):
    def enqueue(
        self, job_type: str, subject_id: str, organization_id: str,
        project_id: str, payload: dict,
    ) -> ServerJob: ...

    def job(self, job_id: str) -> ServerJob | None: ...

    def claim(
        self, lease_seconds: int = 60, max_attempts: int = 3,
        worker_id: str | None = None,
    ) -> ServerJob | None: ...

    def renew(self, job_id: str, lease_token: str, lease_seconds: int = 60) -> bool: ...

    def finish(self, job_id: str, lease_token: str, result: dict) -> bool: ...

    def fail(self, job_id: str, lease_token: str, detail: str) -> bool: ...


class ServerJobStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        try:
            MigrationRunner(SERVER_JOBS_MIGRATIONS, __version__).apply(connection)
            connection.commit()
        finally:
            connection.close()

    def enqueue(
        self, job_type: str, subject_id: str, organization_id: str,
        project_id: str, payload: dict,
    ) -> ServerJob:
        now = datetime.now(UTC).isoformat()
        job = ServerJob(
            str(uuid4()), job_type, subject_id, organization_id, project_id,
            "queued", payload, {}, 0, "", now, now, "", "",
        )
        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute(
                "INSERT INTO server_jobs("
                "job_id,job_type,subject_id,organization_id,project_id,status,"
                "payload_json,result_json,attempts,lease_until_utc,created_at_utc,"
                "updated_at_utc,lease_owner,lease_token"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job.job_id, job.job_type, job.subject_id, job.organization_id,
                    job.project_id, job.status, json.dumps(job.payload, sort_keys=True),
                    "{}", 0, "", now, now, "", "",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return job

    def job(self, job_id: str) -> ServerJob | None:
        connection = sqlite3.connect(self._database_path)
        try:
            row = connection.execute(
                "SELECT * FROM server_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else self._decode(row)

    def claim(
        self,
        lease_seconds: int = 60,
        max_attempts: int = 3,
        worker_id: str | None = None,
    ) -> ServerJob | None:
        now = datetime.now(UTC)
        owner = worker_id or f"worker-{uuid4()}"
        if not owner.strip() or len(owner) > 200:
            raise ValueError("worker_id must contain 1 to 200 characters")
        connection = sqlite3.connect(self._database_path, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT job_id FROM server_jobs WHERE attempts<? AND "
                "(status='queued' OR (status='running' AND lease_until_utc<?)) "
                "ORDER BY created_at_utc,job_id LIMIT 1",
                (max_attempts, now.isoformat()),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            lease = (now + timedelta(seconds=lease_seconds)).isoformat()
            token = str(uuid4())
            connection.execute(
                "UPDATE server_jobs SET status='running',attempts=attempts+1,"
                "lease_until_utc=?,updated_at_utc=?,lease_owner=?,lease_token=? "
                "WHERE job_id=?",
                (lease, now.isoformat(), owner, token, row[0]),
            )
            connection.commit()
            return self.job(str(row[0]))
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def renew(self, job_id: str, lease_token: str, lease_seconds: int = 60) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(UTC)
        connection = sqlite3.connect(self._database_path)
        try:
            cursor = connection.execute(
                "UPDATE server_jobs SET lease_until_utc=?,updated_at_utc=? "
                "WHERE job_id=? AND status='running' AND lease_token=? "
                "AND lease_until_utc>=?",
                (
                    (now + timedelta(seconds=lease_seconds)).isoformat(),
                    now.isoformat(), job_id, lease_token, now.isoformat(),
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def finish(self, job_id: str, lease_token: str, result: dict) -> bool:
        return self._terminal(job_id, lease_token, "succeeded", result)

    def fail(self, job_id: str, lease_token: str, detail: str) -> bool:
        return self._terminal(
            job_id, lease_token, "failed", {"error": detail[:1000]}
        )

    def _terminal(
        self, job_id: str, lease_token: str, status: str, result: dict
    ) -> bool:
        connection = sqlite3.connect(self._database_path)
        try:
            cursor = connection.execute(
                "UPDATE server_jobs SET status=?,result_json=?,lease_until_utc='',"
                "updated_at_utc=?,lease_owner='',lease_token='' "
                "WHERE job_id=? AND status='running' AND lease_token=?",
                (
                    status, json.dumps(result, sort_keys=True),
                    datetime.now(UTC).isoformat(), job_id, lease_token,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    @staticmethod
    def _decode(row) -> ServerJob:
        return ServerJob(
            *row[:6], json.loads(row[6]), json.loads(row[7]), *row[8:]
        )


def run_one_job(
    store: ServerJobRepository,
    search: SearchProjection,
    science_source: Path | ScienceSnapshotRepository | ScienceRecordSource,
    exports: GovernedExportStore | None = None,
    signer: ExportSigningIdentity | None = None,
    worker_id: str | None = None,
    lease_seconds: int = 60,
    staged_ingestion=None,
) -> ServerJob | None:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    job = store.claim(lease_seconds=lease_seconds, worker_id=worker_id)
    if job is None:
        return None
    stop_heartbeat = threading.Event()

    def keep_lease() -> None:
        interval = max(1.0, min(float(lease_seconds) / 3.0, 30.0))
        while not stop_heartbeat.wait(interval):
            if not store.renew(job.job_id, job.lease_token, lease_seconds):
                return

    heartbeat = threading.Thread(
        target=keep_lease,
        name=f"fieldora-job-lease-{job.job_id}",
        daemon=True,
    )
    heartbeat.start()
    try:
        if job.job_type == "rebuild_search":
            count = search.rebuild(science_source, job.organization_id)
            store.finish(
                job.job_id, job.lease_token, {"indexed_records": count}
            )
        elif job.job_type == "staged.validate" and staged_ingestion is not None:
            result = staged_ingestion.validate_file(
                str(job.payload["staged_file_id"])
            )
            submission_id = str(job.payload["submission_id"])
            submission = staged_ingestion.store.submission(submission_id)
            queued: tuple[str, ...] = ()
            if submission is not None and submission.state in {
                "validated",
                "validated_with_rejections",
            }:
                queued = staged_ingestion.queue_processing(submission_id)
            store.finish(
                job.job_id,
                job.lease_token,
                {**result, "processing_job_ids": list(queued)},
            )
        elif job.job_type == "staged.process" and staged_ingestion is not None:
            staged_ids = tuple(str(value) for value in job.payload["staged_file_ids"])
            result = staged_ingestion.process_batch(staged_ids)
            store.finish(job.job_id, job.lease_token, result)
        elif job.job_type == "export_project" and exports is not None:
            repository = (
                SqliteScienceRepository(science_source, default_science_snapshot)
                if isinstance(science_source, Path)
                else science_source
            )
            service = PortableProjectService(ScienceSession(repository))
            include_references = bool(
                job.payload.get("include_library_references", False)
            )
            recipient_public = job.payload.get("recipient_public_key")

            def write_export(destination: Path) -> None:
                if recipient_public is None:
                    service.export_project(
                        job.project_id,
                        destination,
                        include_library_references=include_references,
                    )
                    return
                plaintext = destination.with_suffix(".plaintext.zip")
                try:
                    service.export_project(
                        job.project_id,
                        plaintext,
                        include_library_references=include_references,
                    )
                    encrypt_project_export(plaintext, destination, recipient_public)
                finally:
                    plaintext.unlink(missing_ok=True)

            record = exports.create(
                job.job_id, job.subject_id, job.organization_id, job.project_id,
                write_export,
                filename=(
                    f"fieldora-project-{job.project_id}.fieldora-encrypted"
                    if recipient_public is not None else None
                ),
            )
            attestation = None
            if signer is not None:
                attestation = signer.attest(record.sha256)
                record = exports.attach_attestation(
                    record.export_id,
                    str(attestation["key_id"]),
                    str(attestation["signature"]),
                )
            store.finish(
                job.job_id, job.lease_token,
                {
                    "export_id": record.export_id,
                    "filename": record.filename,
                    "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                    "expires_at_utc": record.expires_at_utc,
                    "attestation": attestation,
                    "encrypted": recipient_public is not None,
                    "recipient_key_id": (
                        str(recipient_public.get("key_id", ""))
                        if recipient_public is not None else ""
                    ),
                },
            )
        else:
            raise ValueError(f"unsupported job type: {job.job_type}")
    except Exception as exc:
        store.fail(job.job_id, job.lease_token, str(exc))
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=2)
    return store.job(job.job_id)
