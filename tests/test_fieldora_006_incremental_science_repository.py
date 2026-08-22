from copy import deepcopy
from pathlib import Path

import pytest

from natureai_next.domain.science import ScienceRevisionConflict
from natureai_next.infrastructure.database.science import SqliteScienceRepository


def _default() -> dict:
    return {
        "schema_version": 3,
        "projects": [],
        "board": [],
        "activities": [],
        "artifacts": [],
        "dossiers": [],
        "project_stages": [],
        "project_activities": [],
        "project_resources": [],
        "project_budgets": [],
        "board_shapes": [],
        "whiteboards": [],
        "whiteboard_elements": [],
        "dossier_whiteboards": [],
    }


def test_repository_writes_only_changed_records(tmp_path: Path) -> None:
    repository = SqliteScienceRepository(tmp_path / "science.sqlite3", _default)
    snapshot, revision = repository.load_snapshot()
    snapshot["projects"].append({"id": "project-1", "name": "Bat survey"})
    revision = repository.save_snapshot(snapshot, expected_revision=revision)
    assert revision.database_revision == 1
    assert repository.record_revision("projects", "project-1") == 1

    unchanged = repository.save_snapshot(snapshot, expected_revision=revision)
    assert unchanged == revision
    assert repository.record_revision("projects", "project-1") == 1

    snapshot["projects"][0]["name"] = "Updated bat survey"
    updated = repository.save_snapshot(snapshot, expected_revision=revision)
    assert updated.database_revision == 2
    assert repository.record_revision("projects", "project-1") == 2


def test_repository_persists_deletions_and_rejects_stale_writers(
    tmp_path: Path,
) -> None:
    repository = SqliteScienceRepository(tmp_path / "science.sqlite3", _default)
    snapshot, revision = repository.load_snapshot()
    snapshot["dossiers"].append({"id": "dossier-1", "title": "Evidence"})
    current = repository.save_snapshot(snapshot, expected_revision=revision)

    stale_snapshot = deepcopy(snapshot)
    snapshot["dossiers"].clear()
    current = repository.save_snapshot(snapshot, expected_revision=current)
    loaded, loaded_revision = repository.load_snapshot()
    assert loaded["dossiers"] == []
    assert loaded_revision == current

    stale_snapshot["dossiers"][0]["title"] = "Stale edit"
    with pytest.raises(ScienceRevisionConflict):
        repository.save_snapshot(stale_snapshot, expected_revision=revision)
