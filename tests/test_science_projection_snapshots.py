from __future__ import annotations

from natureai_next.server.api import ScienceReadProjection


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
