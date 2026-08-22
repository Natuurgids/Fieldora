from pathlib import Path

import pytest

from natureai_next.application.science import ScienceSession, default_science_snapshot
from natureai_next.application.science_packages import PortableProjectService
from natureai_next.domain.science_packages import ProjectCollisionPolicy
from natureai_next.infrastructure.database.science import SqliteScienceRepository


def _session(path: Path) -> ScienceSession:
    return ScienceSession(SqliteScienceRepository(path, default_science_snapshot))


def test_project_package_roundtrip_and_explicit_reference_redaction(
    tmp_path: Path,
) -> None:
    source = _session(tmp_path / "source.sqlite3")
    source.data["projects"].append({"id": "p1", "name": "Bat survey"})
    source.data["dossiers"].append(
        {
            "id": "d1", "title": "Night one", "project_id": "p1",
            "media_ids": ["asset-1"],
        }
    )
    source.save()
    service = PortableProjectService(source)
    package = tmp_path / "project.fieldora-project.zip"
    summary = service.export_project(
        "p1", package, include_library_references=False
    )
    assert summary.library_reference_count == 0
    assert not summary.includes_originals

    target = _session(tmp_path / "target.sqlite3")
    imported = PortableProjectService(target)
    plan = imported.plan_import(package, policy=ProjectCollisionPolicy.FAIL)
    assert plan.can_apply
    imported.import_project(package, policy=ProjectCollisionPolicy.FAIL)
    assert target.data["projects"][0]["id"] == "p1"
    assert target.data["dossiers"][0]["media_ids"] == []


def test_collision_fail_does_not_change_target(tmp_path: Path) -> None:
    source = _session(tmp_path / "source.sqlite3")
    source.data["projects"].append({"id": "p1", "name": "Incoming"})
    source.save()
    package = tmp_path / "project.zip"
    PortableProjectService(source).export_project(
        "p1", package, include_library_references=True
    )

    target = _session(tmp_path / "target.sqlite3")
    target.data["projects"].append({"id": "p1", "name": "Existing"})
    target.save()
    service = PortableProjectService(target)
    with pytest.raises(ValueError):
        service.import_project(package, policy=ProjectCollisionPolicy.FAIL)
    assert target.data["projects"] == [{"id": "p1", "name": "Existing"}]
