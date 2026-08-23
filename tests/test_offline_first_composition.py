from __future__ import annotations

import os
from pathlib import Path

import pytest

from natureai_next.bootstrap.platform_server_cli import _offline_sync_factory
from natureai_next.server.offline_sync import OfflineSyncStore
from natureai_next.server.postgres_offline_sync import PostgresOfflineSyncStore


def test_standalone_server_uses_normal_local_subsystem_store(tmp_path: Path) -> None:
    factory = _offline_sync_factory(
        ["serve", "--data-root", str(tmp_path), "--science-backend", "sqlite"],
        "serve",
    )
    assert factory is not None
    store = factory()
    assert isinstance(store, OfflineSyncStore)
    assert (tmp_path / "databases" / "offline-sync.sqlite3").is_file()


def test_non_server_commands_do_not_construct_sync_repository(tmp_path: Path) -> None:
    assert _offline_sync_factory(["init-user", "--data-root", str(tmp_path)], "init-user") is None


@pytest.mark.integration
def test_postgres_server_uses_shared_science_database_for_sync(tmp_path: Path) -> None:
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    pytest.importorskip("psycopg")
    dsn_file = tmp_path / "science.dsn"
    dsn_file.write_text(dsn, encoding="utf-8")

    factory = _offline_sync_factory(
        [
            "serve",
            "--science-backend",
            "postgresql",
            "--postgres-science-dsn-file",
            str(dsn_file),
        ],
        "serve",
    )
    assert factory is not None
    store = factory()
    assert isinstance(store, PostgresOfflineSyncStore)
