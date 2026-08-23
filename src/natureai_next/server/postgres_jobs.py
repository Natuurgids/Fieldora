"""PostgreSQL server-job repository with fenced, skip-locked claims."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from natureai_next.server.jobs import ServerJob


class PostgresServerJobStore:
    """Shared job repository suitable for independently deployed workers."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                # API and worker processes can start together on a clean database.
                # PostgreSQL's CREATE TABLE IF NOT EXISTS is not enough to protect
                # concurrent catalog/type creation, so serialize this schema bootstrap
                # transaction with a stable advisory lock.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_server_jobs_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS server_jobs(
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json JSONB NOT NULL,
                        result_json JSONB NOT NULL,
                        attempts INTEGER NOT NULL,
                        lease_until_utc TIMESTAMPTZ,
                        created_at_utc TIMESTAMPTZ NOT NULL,
                        updated_at_utc TIMESTAMPTZ NOT NULL,
                        lease_owner TEXT NOT NULL DEFAULT '',
                        lease_token TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_server_jobs_claim_pg "
                    "ON server_jobs(status,lease_until_utc,attempts,created_at_utc)"
                )

    def enqueue(
        self,
        job_type: str,
        subject_id: str,
        organization_id: str,
        project_id: str,
        payload: dict,
    ) -> ServerJob:
        now = datetime.now(UTC)
        job_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO server_jobs(
                        job_id,job_type,subject_id,organization_id,project_id,status,
                        payload_json,result_json,attempts,lease_until_utc,
                        created_at_utc,updated_at_utc,lease_owner,lease_token
                    )
                    VALUES(%s,%s,%s,%s,%s,'queued',%s::jsonb,%s::jsonb,0,
                           NULL,%s,%s,'','')
                    """,
                    (
                        job_id,
                        job_type,
                        subject_id,
                        organization_id,
                        project_id,
                        json.dumps(payload, sort_keys=True),
                        "{}",
                        now,
                        now,
                    ),
                )
        result = self.job(job_id)
        if result is None:
            raise RuntimeError("PostgreSQL job enqueue did not persist")
        return result

    def claim(self, *, lease_seconds: int, worker_id: str = "worker") -> ServerJob | None:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(1, lease_seconds))
        lease_token = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT job_id
                        FROM server_jobs
                        WHERE attempts < 3
                          AND (
                            status='queued'
                            OR (status='running' AND lease_until_utc < %s)
                          )
                        ORDER BY created_at_utc, job_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE server_jobs AS jobs
                    SET status='running', attempts=jobs.attempts+1,
                        lease_until_utc=%s, updated_at_utc=%s,
                        lease_owner=%s, lease_token=%s
                    FROM candidate
                    WHERE jobs.job_id=candidate.job_id
                    RETURNING
                        jobs.job_id,jobs.job_type,jobs.subject_id,
                        jobs.organization_id,jobs.project_id,jobs.status,
                        jobs.payload_json,jobs.result_json,jobs.attempts,
                        jobs.lease_until_utc,jobs.created_at_utc,
                        jobs.updated_at_utc,jobs.lease_owner,jobs.lease_token
                    """,
                    (now, lease_until, now, worker_id, lease_token),
                )
                row = cursor.fetchone()
        return None if row is None else _row_to_job(row)

    def finish(self, job_id: str, lease_token: str, result: dict) -> bool:
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE server_jobs
                    SET status='succeeded',result_json=%s::jsonb,
                        lease_until_utc=NULL,updated_at_utc=%s,
                        lease_owner='',lease_token=''
                    WHERE job_id=%s AND status='running' AND lease_token=%s
                    """,
                    (json.dumps(result, sort_keys=True), now, job_id, lease_token),
                )
                return cursor.rowcount == 1

    def fail(self, job_id: str, lease_token: str, result: dict) -> bool:
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE server_jobs
                    SET status=CASE WHEN attempts >= 3 THEN 'failed' ELSE 'queued' END,
                        result_json=%s::jsonb,lease_until_utc=NULL,updated_at_utc=%s,
                        lease_owner='',lease_token=''
                    WHERE job_id=%s AND status='running' AND lease_token=%s
                    """,
                    (json.dumps(result, sort_keys=True), now, job_id, lease_token),
                )
                return cursor.rowcount == 1

    def job(self, job_id: str) -> ServerJob | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT job_id,job_type,subject_id,organization_id,project_id,status,
                           payload_json,result_json,attempts,lease_until_utc,
                           created_at_utc,updated_at_utc,lease_owner,lease_token
                    FROM server_jobs WHERE job_id=%s
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()
        return None if row is None else _row_to_job(row)


def _row_to_job(row: Any) -> ServerJob:
    lease_until = row[9]
    return ServerJob(
        job_id=str(row[0]),
        job_type=str(row[1]),
        subject_id=str(row[2]),
        organization_id=str(row[3]),
        project_id=str(row[4]),
        status=str(row[5]),
        payload=dict(row[6] or {}),
        result=dict(row[7] or {}),
        attempts=int(row[8]),
        lease_until_utc=(lease_until.isoformat() if lease_until is not None else ""),
        created_at_utc=row[10].isoformat(),
        updated_at_utc=row[11].isoformat(),
        lease_owner=str(row[12] or ""),
        lease_token=str(row[13] or ""),
    )
