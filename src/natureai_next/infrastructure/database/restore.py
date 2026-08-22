"""Windows-safe SQLite restore validation and atomic replacement."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

RestoreRetryLogger = Callable[[int, OSError], None]


def validate_database_and_close(database: Path) -> None:
    """Validate SQLite integrity and foreign keys, releasing all handles on return."""
    connection: sqlite3.Connection | None = None
    cursor: sqlite3.Cursor | None = None
    try:
        connection = sqlite3.connect(str(database))
        cursor = connection.cursor()
        result = cursor.execute("PRAGMA integrity_check").fetchone()
        if result is None or str(result[0]).casefold() != "ok":
            raise RuntimeError(f"Restored database integrity check failed: {result}")
        foreign_keys = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError(
                f"Restored database contains {len(foreign_keys)} foreign-key violation(s)"
            )
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def replace_database_with_retry(
    source: Path,
    target: Path,
    *,
    attempts: int = 5,
    retry_logger: RestoreRetryLogger | None = None,
) -> None:
    """Atomically replace target, tolerating short-lived Windows file scanners."""
    delays = (0.0, 0.25, 0.5, 1.0, 1.5)
    last_error: OSError | None = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            time.sleep(delays[min(attempt - 1, len(delays) - 1)])
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            last_error = exc
            if retry_logger is not None:
                retry_logger(attempt, exc)
    assert last_error is not None
    raise last_error
