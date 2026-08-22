import sqlite3
from pathlib import Path

import pytest

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


def test_read_and_write_connections_use_the_same_database(tmp_path: Path) -> None:
    database = tmp_path / "folder with spaces # and unicode ü" / "library.sqlite3"
    factory = SqliteConnectionFactory(database)
    writable = factory.connect()
    try:
        writable.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY)")
    finally:
        writable.close()

    readable = factory.connect(read_only=True)
    try:
        assert (
            readable.execute("SELECT name FROM sqlite_master WHERE name='observations'").fetchone()[
                0
            ]
            == "observations"
        )
        assert (
            Path(readable.execute("PRAGMA database_list").fetchone()[2])
            .resolve()
            .samefile(database)
        )
        with pytest.raises(sqlite3.OperationalError):
            readable.execute("CREATE TABLE forbidden(id INTEGER)")
    finally:
        readable.close()


def test_read_only_connection_never_creates_a_missing_database(tmp_path: Path) -> None:
    database = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        SqliteConnectionFactory(database).connect(read_only=True)
    assert not database.exists()
