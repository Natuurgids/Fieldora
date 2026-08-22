from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_specimen_encounter_timeline_merge_and_dossier_context(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project = service.create_project("Longitudinal study", owner_id="owner", actor_id="owner")
    canonical = service.create_specimen(project, specimen_code="A-001", taxon_name="Turdus merula", actor_id="owner")
    duplicate = service.create_specimen(project, specimen_code="TMP-9", taxon_name="Turdus merula", actor_id="owner")
    service.add_specimen_identifier(duplicate, identifier_type="ring", identifier_value="NL-123", actor_id="owner")
    encounter = service.create_specimen_encounter(project, duplicate, encounter_type="capture", occurred_at="2026-08-03T10:00:00+00:00", location_name="Site A", actor_id="owner")
    service.record_specimen_enrichment(project, duplicate, enrichment_type="measurement", value_text="92", unit="g", occurred_at="2026-08-03T10:05:00+00:00", actor_id="owner")
    sample = service.create_sample(project, sample_code="BLOOD-1", sample_type="blood", specimen_code="TMP-9", actor_id="owner")

    before = service.specimen_timeline(duplicate, actor_id="owner")
    assert {row["kind"] for row in before} >= {"encounter", "enrichment", "identifier", "sample"}

    service.merge_specimens(canonical, duplicate, actor_id="owner", reason="same ring and capture history")
    assert {row["specimen_id"] for row in service.specimen_encounters(project)} == {canonical}
    assert {row["specimen_id"] for row in service.specimen_enrichments(project)} == {canonical}
    assert service.samples(project)[0]["specimen_code"] == "A-001"
    assert any(row["event_type"] == "specimen.merged" for row in service.activity(project))

    link = service.link_dossier_context("DOSSIER-1", project, "specimen", canonical, actor_id="owner")
    assert link
    context = service.dossier_context("DOSSIER-1")
    assert context[0]["context_type"] == "specimen"
    assert context[0]["context_id"] == canonical
    assert any(row["event_type"] == "dossier.context_linked" for row in service.activity(project))
