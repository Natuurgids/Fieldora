from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from natureai_next.application.science import default_science_snapshot
from natureai_next.domain.science import ScienceRevision
from natureai_next.infrastructure.database.science import SqliteScienceRepository


class _PausingRevisionCursor:
    def __init__(
        self,
        cursor,
        revision_read: threading.Event,
        continue_read: threading.Event,
    ) -> None:
        self._cursor = cursor
        self._revision_read = revision_read
        self._continue_read = continue_read

    def fetchone(self):
        row = self._cursor.fetchone()
        self._revision_read.set()
        assert self._continue_read.wait(timeout=10)
        return row


class _PausingReadConnection:
    def __init__(
        self,
        connection,
        revision_read: threading.Event,
        continue_read: threading.Event,
    ) -> None:
        self._connection = connection
        self._revision_read = revision_read
        self._continue_read = continue_read

    def execute(self, statement: str, parameters=()):
        cursor = self._connection.execute(statement, parameters)
        if statement.startswith("SELECT revision FROM science_state"):
            return _PausingRevisionCursor(
                cursor,
                self._revision_read,
                self._continue_read,
            )
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def test_sqlite_load_snapshot_keeps_revision_and_records_from_one_commit(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "science.db"
    reader = SqliteScienceRepository(database_path, default_science_snapshot)
    writer = SqliteScienceRepository(database_path, default_science_snapshot)

    initial = default_science_snapshot()
    initial["projects"] = [{"id": "project-1", "name": "Before"}]
    revision_one = writer.save_snapshot(
        initial,
        expected_revision=ScienceRevision(0),
    )
    assert revision_one == ScienceRevision(1)

    replacement = deepcopy(initial)
    replacement["projects"] = [{"id": "project-1", "name": "After"}]

    revision_read = threading.Event()
    continue_read = threading.Event()
    real_connect = reader._factory.connect

    def paused_connect(*, read_only: bool = False):
        connection = real_connect(read_only=read_only)
        if not read_only:
            return connection
        return _PausingReadConnection(connection, revision_read, continue_read)

    monkeypatch.setattr(reader._factory, "connect", paused_connect)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(reader.load_snapshot)
        assert revision_read.wait(timeout=10)
        revision_two = writer.save_snapshot(
            replacement,
            expected_revision=revision_one,
        )
        continue_read.set()
        loaded, loaded_revision = future.result(timeout=10)

    assert revision_two == ScienceRevision(2)
    assert loaded_revision == revision_one
    assert loaded["projects"] == [{"id": "project-1", "name": "Before"}]

    latest, latest_revision = writer.load_snapshot()
    assert latest_revision == revision_two
    assert latest["projects"] == [{"id": "project-1", "name": "After"}]
