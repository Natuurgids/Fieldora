from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService
from natureai_next.application.science import ScienceSession, default_science_snapshot
from natureai_next.infrastructure.database.science import SqliteScienceRepository


def test_science_repository_persists_master_dossier_links(tmp_path: Path):
    repository = SqliteScienceRepository(tmp_path / "science.sqlite3", default_science_snapshot)
    session = ScienceSession(repository)
    session.data["dossiers"].extend(
        [
            {"id": "master", "title": "Master", "dossier_type": "master"},
            {"id": "child", "title": "Child", "dossier_type": "dossier"},
        ]
    )
    session.data["dossier_links"].append(
        {
            "id": "link-1",
            "parent_dossier_id": "master",
            "child_dossier_id": "child",
            "relationship": "contains",
        }
    )
    session.save()

    loaded = ScienceSession(repository).data
    assert loaded["dossier_links"] == [
        {
            "id": "link-1",
            "parent_dossier_id": "master",
            "child_dossier_id": "child",
            "relationship": "contains",
        }
    ]


def test_dossier_can_link_all_research_context_types(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "project.sqlite3")
    project = service.create_project("Dossier project", owner_id="owner", actor_id="owner")
    context_types = (
        "specimen", "identifier", "encounter", "survey_event", "protocol",
        "definition", "enrichment", "sample", "laboratory", "laboratory_media",
    )
    for index, context_type in enumerate(context_types):
        link_id = service.link_dossier_context(
            "dossier-1", project, context_type, f"item-{index}", actor_id="owner"
        )
        assert link_id
    assert {row["context_type"] for row in service.dossier_context("dossier-1")} == set(context_types)


def test_dossier_ui_uses_accessible_projects_description_and_science_tabs():
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    assert "def _accessible_dossier_projects" in source
    assert "self._workspace_context.accessible_projects" in source
    assert 'form.addRow("Description", self._dossier_description)' in source
    for label in ("Specimens", "Survey events", "Protocols", "Enrichments", "Samples", "Laboratory", "Lab media"):
        assert f'"{label}"' in source
    assert "Master dossier" in source
    assert "dossier_links" in source
    assert "Length (mm)" not in source[source.index("def _dossiers_page"):source.index("def _whiteboard_page")]
