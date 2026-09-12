from __future__ import annotations

import os
from pathlib import Path

import pytest

from natureai_next.bootstrap.platform_server_cli import (
    _linked_storage_factory,
    _offline_sync_factory,
)
from natureai_next.server.offline_sync import OfflineSyncStore
from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.postgres_offline_sync import PostgresOfflineSyncStore


def test_standalone_server_uses_normal_local_subsystem_store(tmp_path: Path) -> None:
    factory = _offline_sync_factory(
        ["serve", "--data-root", str(tmp_path), "--science-backend", "sqlite"],
        "serve",
    )
    assert factory is not None
    store = factory()
    assert isinstance(store, OfflineSyncStore)
    assert (tmp_path / "subsystems" / "offline-sync.sqlite3").is_file()


def test_standalone_server_does_not_fake_shared_linked_storage_catalogue(tmp_path: Path) -> None:
    assert (
        _linked_storage_factory(
            ["serve", "--data-root", str(tmp_path), "--science-backend", "sqlite"],
            "serve",
        )
        is None
    )


def test_non_server_commands_do_not_construct_offline_first_repositories(tmp_path: Path) -> None:
    arguments = ["init-user", "--data-root", str(tmp_path)]
    assert _offline_sync_factory(arguments, "init-user") is None
    assert _linked_storage_factory(arguments, "init-user") is None


@pytest.mark.integration
def test_postgres_server_uses_shared_science_database_for_sync_and_catalogue(tmp_path: Path) -> None:
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    pytest.importorskip("psycopg")
    dsn_file = tmp_path / "science.dsn"
    dsn_file.write_text(dsn, encoding="utf-8")
    arguments = [
        "serve",
        "--science-backend",
        "postgresql",
        "--postgres-science-dsn-file",
        str(dsn_file),
    ]

    sync_factory = _offline_sync_factory(arguments, "serve")
    linked_factory = _linked_storage_factory(arguments, "serve")
    assert sync_factory is not None
    assert linked_factory is not None
    assert isinstance(sync_factory(), PostgresOfflineSyncStore)
    assert isinstance(linked_factory(), PostgresLinkedStorageRepository)
