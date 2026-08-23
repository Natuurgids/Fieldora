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
            raise RuntimeError("PostgreSQL did not retain the queued job")
        return result

    def job(self, job_id: str) -> ServerJob | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT job_id,job_type,subject_id,organization_id,project_id,status,
                           payload_json,result_json,attempts,lease_until_utc,
                           created_at_utc,updated_at_utc,lease_owner,lease_token
                    FROM server_jobs
                    WHERE job_id=%s
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()
        return None if row is None else self._decode(row)

    def claim(
        self,
        lease_seconds: int = 60,
        max_attempts: int = 3,
        worker_id: str | None = None,
    ) -> ServerJob | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        owner = worker_id or f"worker-{uuid4()}"
        if not owner.strip() or len(owner) > 200:
            raise ValueError("worker_id must contain 1 to 200 characters")
        now = datetime.now(UTC)
        lease = now + timedelta(seconds=lease_seconds)
        token = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT job_id
                        FROM server_jobs
                        WHERE attempts<%s
                          AND (
                            status='queued'
                            OR (status='running' AND lease_until_utc<%s)
                          )
                        ORDER BY created_at_utc,job_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE server_jobs AS jobs
                    SET status='running',
                        attempts=jobs.attempts+1,
                        lease_until_utc=%s,
                        updated_at_utc=%s,
                        lease_owner=%s,
                        lease_token=%s
                    FROM candidate
                    WHERE jobs.job_id=candidate.job_id
                    RETURNING
                        jobs.job_id,jobs.job_type,jobs.subject_id,
                        jobs.organization_id,jobs.project_id,jobs.status,
                        jobs.payload_json,jobs.result_json,jobs.attempts,
                        jobs.lease_until_utc,jobs.created_at_utc,
                        jobs.updated_at_utc,jobs.lease_owner,jobs.lease_token
                    """,
                    (max_attempts, now, lease, now, owner, token),
                )
                row = cursor.fetchone()
        return None if row is None else self._decode(row)

    def renew(self, job_id: str, lease_token: str, lease_seconds: int = 60) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE server_jobs SET lease_until_utc=%s,updated_at_utc=%s "
                    "WHERE job_id=%s AND status='running' AND lease_token=%s "
                    "AND lease_until_utc>=%s",
                    (
                        now + timedelta(seconds=lease_seconds),
                        now,
                        job_id,
                        lease_token,
                        now,
                    ),
                )
                return cursor.rowcount == 1

    def finish(self, job_id: str, lease_token: str, result: dict) -> bool:
        return self._terminal(job_id, lease_token, "succeeded", result)

    def fail(self, job_id: str, lease_token: str, detail: str) -> bool:
        return self._terminal(
            job_id, lease_token, "failed", {"error": detail[:1000]}
        )

    def _terminal(
        self, job_id: str, lease_token: str, status: str, result: dict
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE server_jobs SET status=%s,result_json=%s::jsonb,"
                    "lease_until_utc=NULL,updated_at_utc=%s,lease_owner='',"
                    "lease_token='' WHERE job_id=%s AND status='running' "
                    "AND lease_token=%s",
                    (
                        status,
                        json.dumps(result, sort_keys=True),
                        datetime.now(UTC),
                        job_id,
                        lease_token,
                    ),
                )
                return cursor.rowcount == 1

    @staticmethod
    def _decode(row: Any) -> ServerJob:
        values = list(row)
        for index in (6, 7):
            if isinstance(values[index], str):
                values[index] = json.loads(values[index])
        for index in (9, 10, 11):
            value = values[index]
            values[index] = "" if value is None else (
                value.isoformat() if hasattr(value, "isoformat") else str(value)
            )
        return ServerJob(*values)
