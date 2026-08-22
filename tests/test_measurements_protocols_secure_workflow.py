from pathlib import Path

import pytest

from natureai_next.application.project_management import ProjectManagementService


def test_cross_project_links_are_rejected_and_activity_is_auditable(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    a = service.create_project("A", owner_id="alice", actor_id="alice")
    b = service.create_project("B", owner_id="bob", actor_id="bob")
    sample_b = service.create_sample(b, sample_code="B-1", sample_type="blood", actor_id="bob")
    definition_b = service.create_measurement_definition(
        b, name="Mass", category="mammal", unit="kg", actor_id="bob"
    )

    with pytest.raises(ValueError, match="another project"):
        service.record_measurement(
            a, name="Mass", value="1", unit="kg", sample_id=sample_b, actor_id="alice"
        )
    with pytest.raises(ValueError, match="another project"):
        service.record_measurement(
            a, name="Mass", value="1", unit="kg", definition_id=definition_b, actor_id="alice"
        )

    sample_a = service.create_sample(a, sample_code="A-1", sample_type="blood", actor_id="alice")
    definition_a = service.create_measurement_definition(
        a, name="Mass", category="mammal", unit="kg", actor_id="alice"
    )
    with pytest.raises(ValueError, match="numeric"):
        service.record_measurement(
            a, name="Mass", value="not-a-number", unit="kg",
            sample_id=sample_a, definition_id=definition_a, actor_id="alice"
        )
    service.record_measurement(
        a, name="Mass", value="2.3", unit="kg",
        sample_id=sample_a, definition_id=definition_a, actor_id="alice"
    )
    assert any(row["event_type"] == "measurement.recorded" for row in service.activity(a))


def test_rbac_abac_pbac_effective_decision_and_project_filtering(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project = service.create_project("Restricted", owner_id="owner", actor_id="owner")
    service.set_member_role(project, "viewer", "guest", actor_id="owner")

    snapshot = service.authorization_snapshot(project, "viewer")
    assert snapshot["role"] == "guest"
    assert snapshot["rbac"] is True
    assert snapshot["pbac_default"] == "deny"
    assert service.can(project, "viewer", "view")
    assert not service.can(project, "viewer", "edit")
    assert [row["project_id"] for row in service.accessible_projects("viewer")] == [project]

    with pytest.raises(PermissionError):
        service.create_sample(project, sample_code="X", sample_type="water", actor_id="viewer")

    with service._connect() as connection:
        connection.execute("UPDATE pm_projects SET status='archived' WHERE project_id=?", (project,))
    service.set_member_role(project, "editor", "contributor", actor_id="owner")
    assert not service.can(project, "editor", "edit")
    with pytest.raises(PermissionError, match="archived"):
        service.create_sample(project, sample_code="Y", sample_type="water", actor_id="editor")


def test_csv_import_is_atomic(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project = service.create_project("CSV", owner_id="owner", actor_id="owner")
    source = tmp_path / "bad.csv"
    source.write_text("name,value,unit,uncertainty\npH,7,pH,0.1\nTemp,20,C,bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row 3"):
        service.import_instrument_csv(project, source, actor_id="owner")
    assert service.measurements(project) == ()


def test_quality_findings_are_resolved_when_problem_is_fixed(tmp_path: Path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project = service.create_project("Quality", owner_id="owner", actor_id="owner")
    sample = service.create_sample(project, sample_code="S", sample_type="water", actor_id="owner")
    service.run_quality_checks(project, actor_id="owner")
    assert any(row["state"] == "open" for row in service.quality_findings(project))
    with service._connect() as connection:
        connection.execute(
            "UPDATE pm_samples SET collected_at='2026-08-03T10:00:00+00:00',latitude=1,longitude=2 WHERE sample_id=?",
            (sample,),
        )
    service.run_quality_checks(project, actor_id="owner")
    assert all(row["state"] != "open" for row in service.quality_findings(project))
