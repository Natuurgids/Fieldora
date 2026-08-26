from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_science import PostgresScienceRepository


def _dsn() -> str:
    value = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not value:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    return value


def _run_concurrently(factory) -> None:
    barrier = threading.Barrier(8)

    def initialize() -> None:
        barrier.wait(timeout=10)
        factory()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(initialize) for _ in range(8)]
        for future in futures:
            future.result(timeout=30)


def test_science_schema_bootstrap_is_safe_for_concurrent_api_and_worker_start() -> None:
    dsn = _dsn()
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("DROP TABLE IF EXISTS science_records CASCADE")
        connection.execute("DROP TABLE IF EXISTS science_state CASCADE")

    _run_concurrently(
        lambda: PostgresScienceRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    )

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        state = connection.execute(
            "SELECT revision FROM science_state WHERE singleton=TRUE"
        ).fetchone()
    assert state == (0,)


def test_media_schema_bootstrap_is_safe_for_concurrent_api_and_worker_start() -> None:
    dsn = _dsn()
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("DROP TABLE IF EXISTS governed_media_associations CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_media_instances CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_uploads CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_media CASCADE")

    _run_concurrently(
        lambda: PostgresMediaMetadataRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    )

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        media = connection.execute("SELECT count(*) FROM governed_media").fetchone()
        instances = connection.execute(
            "SELECT count(*) FROM governed_media_instances"
        ).fetchone()
        uploads = connection.execute("SELECT count(*) FROM governed_uploads").fetchone()
        associations = connection.execute(
            "SELECT count(*) FROM governed_media_associations"
        ).fetchone()
    assert media == (0,)
    assert instances == (0,)
    assert uploads == (0,)
    assert associations == (0,)
