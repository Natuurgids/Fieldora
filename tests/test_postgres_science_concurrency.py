from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from natureai_next.server.postgres_science import PostgresScienceRepository


def _dsn() -> str:
    value = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not value:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    return value


def test_science_schema_bootstrap_is_safe_for_concurrent_api_and_worker_start() -> None:
    dsn = _dsn()
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("DROP TABLE IF EXISTS science_records CASCADE")
        connection.execute("DROP TABLE IF EXISTS science_state CASCADE")

    barrier = threading.Barrier(8)

    def initialize() -> None:
        barrier.wait(timeout=10)
        PostgresScienceRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(initialize) for _ in range(8)]
        for future in futures:
            future.result(timeout=30)

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        state = connection.execute(
            "SELECT revision FROM science_state WHERE singleton=TRUE"
        ).fetchone()
    assert state == (0,)
