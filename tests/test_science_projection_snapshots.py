from __future__ import annotations

from natureai_next.server.api import ScienceReadProjection
from natureai_next.server.postgres_science import PostgresScienceRepository


def test_science_projection_snapshot_round_trip(tmp_path) -> None:
    projection = ScienceReadProjection(tmp_path / "science.sqlite3")

    snapshot, revision = projection.load_snapshot()
    assert revision.database_revision == 0
    assert snapshot["schema_version"] == 4

    snapshot["projects"] = [{"id": "project-1", "name": "First project"}]
    saved_revision = projection.save_snapshot(snapshot, expected_revision=revision)

    reloaded, reloaded_revision = projection.load_snapshot()
    assert saved_revision.database_revision == 1
    assert reloaded_revision == saved_revision
    assert reloaded["projects"] == [{"id": "project-1", "name": "First project"}]


def test_science_projection_snapshot_save_replaces_removed_records(tmp_path) -> None:
    projection = ScienceReadProjection(tmp_path / "science.sqlite3")

    snapshot, revision = projection.load_snapshot()
    snapshot["projects"] = [{"id": "project-1", "name": "First project"}]
    revision = projection.save_snapshot(snapshot, expected_revision=revision)

    replacement, loaded_revision = projection.load_snapshot()
    assert loaded_revision == revision
    replacement["projects"] = [{"id": "project-2", "name": "Replacement project"}]
    next_revision = projection.save_snapshot(
        replacement,
        expected_revision=loaded_revision,
    )

    reloaded, reloaded_revision = projection.load_snapshot()
    assert next_revision.database_revision == revision.database_revision + 1
    assert reloaded_revision == next_revision
    assert reloaded["projects"] == [
        {"id": "project-2", "name": "Replacement project"}
    ]
    assert projection.records("projects") == (
        {"id": "project-2", "name": "Replacement project"},
    )


class _SnapshotCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self._revision_read = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query, _params=None) -> None:
        self.queries.append(" ".join(str(query).split()))

    def fetchone(self):
        self._revision_read = True
        return (7,)

    def fetchall(self):
        assert self._revision_read
        return [("projects", {"id": "project-1", "name": "Pinned"})]


class _SnapshotConnection:
    def __init__(self, cursor: _SnapshotCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self) -> _SnapshotCursor:
        return self._cursor


def test_postgres_load_snapshot_locks_revision_until_records_are_read() -> None:
    cursor = _SnapshotCursor()
    repository = object.__new__(PostgresScienceRepository)
    repository._connect = lambda: _SnapshotConnection(cursor)

    snapshot, revision = repository.load_snapshot()

    assert revision.database_revision == 7
    assert snapshot["projects"] == [{"id": "project-1", "name": "Pinned"}]
    assert cursor.queries == [
        "SELECT revision FROM science_state WHERE singleton=TRUE FOR SHARE",
        "SELECT collection_name,payload_json FROM science_records ORDER BY collection_name,updated_at_us,record_id",
    ]
