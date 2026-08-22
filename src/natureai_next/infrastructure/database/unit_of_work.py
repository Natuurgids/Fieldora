"""Explicit SQLite unit of work with writes serialized per database file."""

from __future__ import annotations

import sqlite3
import threading
import weakref
from pathlib import Path
from types import TracebackType

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.repositories import (
    SqliteAssetRepository,
    SqliteAuditRepository,
    SqliteCollectionRepository,
    SqliteFileInstanceRepository,
    SqliteJobRepository,
    SqliteOutboxRepository,
    SqliteTagRepository,
)


class _DatabaseWriteLocks:
    """Provide one re-entrant writer gate per resolved SQLite path."""

    _guard = threading.Lock()
    _locks: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()

    @classmethod
    def for_path(cls, path: Path) -> threading.RLock:
        key = str(path.expanduser().resolve(strict=False)).casefold()
        with cls._guard:
            lock = cls._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._locks[key] = lock
            return lock


class SqliteUnitOfWork:
    """Transaction boundary that never serializes unrelated databases."""

    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self.factory = factory
        self.connection: sqlite3.Connection | None = None
        self._write_lock = _DatabaseWriteLocks.for_path(factory.database_path)
        self._lock_held = False

    def __enter__(self) -> SqliteUnitOfWork:
        self._write_lock.acquire()
        self._lock_held = True
        try:
            self.connection = self.factory.connect()
            self.connection.execute("BEGIN IMMEDIATE")
            connection = self.connection
            self.assets = SqliteAssetRepository(connection)
            self.files = SqliteFileInstanceRepository(connection)
            self.tags = SqliteTagRepository(connection)
            self.collections = SqliteCollectionRepository(connection)
            self.jobs = SqliteJobRepository(connection)
            self.outbox = SqliteOutboxRepository(connection)
            self.audit = SqliteAuditRepository(connection)
            return self
        except Exception:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            self._release_lock()
            raise

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("unit of work is not active")
        self.connection.execute("COMMIT")

    def rollback(self) -> None:
        if self.connection is not None and self.connection.in_transaction:
            self.connection.execute("ROLLBACK")

    def _release_lock(self) -> None:
        if self._lock_held:
            self._lock_held = False
            self._write_lock.release()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self.connection is not None:
                if exc_type is not None or self.connection.in_transaction:
                    self.rollback()
                self.connection.close()
        finally:
            self.connection = None
            self._release_lock()
