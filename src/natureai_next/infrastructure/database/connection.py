"""Thread-confined SQLite connection factory.

All connections are verified against the same canonical filesystem path. Read-only
connections use a properly escaped Path.as_uri() SQLite URI with mode=ro and are
then checked with PRAGMA database_list.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.settings import SqliteSettings


class SqliteConnectionFactory:
    def __init__(self, database_path: Path, settings: SqliteSettings | None = None) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.settings = settings or SqliteSettings()

    @staticmethod
    def _same_file(left: Path, right: Path) -> bool:
        try:
            return left.samefile(right)
        except (FileNotFoundError, OSError):
            return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))

    def _assert_connected_database(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("PRAGMA database_list").fetchone()
        if row is None or not row[2]:
            raise sqlite3.DatabaseError("SQLite did not report the opened main database path")
        actual = Path(str(row[2])).expanduser().resolve()
        if not self._same_file(actual, self.database_path):
            connection.close()
            raise sqlite3.DatabaseError(
                f"SQLite opened an unexpected database: expected {self.database_path}, got {actual}"
            )

    def connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        # Use the exact same absolute Path object for every connection.  For a
        # logical read-only connection, require the file to exist and enable
        # SQLite query_only rather than switching to a second URI namespace.
        if read_only and not self.database_path.is_file():
            raise FileNotFoundError(f"SQLite database does not exist: {self.database_path}")
        if not read_only:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        target: str | Path
        use_uri = False
        if read_only:
            # Path.as_uri() correctly escapes spaces, #, Unicode, and Windows drive paths.
            target = self.database_path.as_uri() + "?mode=ro"
            use_uri = True
        else:
            target = self.database_path
        connection = sqlite3.connect(
            target,
            isolation_level=None,
            check_same_thread=True,
            uri=use_uri,
        )
        connection.row_factory = sqlite3.Row
        self._assert_connected_database(connection)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={self.settings.busy_timeout_ms}")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(f"PRAGMA cache_size={-self.settings.cache_size_kib}")
        connection.execute(f"PRAGMA mmap_size={self.settings.mmap_size_bytes}")
        if read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(f"PRAGMA synchronous={self.settings.synchronous}")
        return connection
