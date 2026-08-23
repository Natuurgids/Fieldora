from __future__ import annotations

import os

import psycopg
import pytest

from natureai_next.server.postgres_jobs import PostgresServerJobStore


def _dsn() -> str:
    value = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not value:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    return value


def test_worker_can_claim_and_finish_postgres_job() -> None:
    dsn = _dsn()
    store = PostgresServerJobStore(lambda: psycopg.connect(dsn, connect_timeout=10))
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("TRUNCATE TABLE server_jobs")

    queued = store.enqueue(
        "test.noop",
        "subject-1",
        "org-1",
        "project-1",
        {"test": True},
    )

    claimed = store.claim(lease_seconds=60, worker_id="fieldora-worker-test")

    assert claimed is not None
    assert claimed.job_id == queued.job_id
    assert claimed.status == "running"
    assert claimed.lease_owner == "fieldora-worker-test"
    assert claimed.lease_token
    assert claimed.attempts == 1

    assert store.finish(claimed.job_id, claimed.lease_token, {"ok": True})
    finished = store.job(claimed.job_id)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.result == {"ok": True}
