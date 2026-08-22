from pathlib import Path

from natureai_next.application.phase4_administration import Phase4AdministrationService


def service(tmp_path: Path) -> Phase4AdministrationService:
    db = tmp_path / "science.sqlite3"
    return Phase4AdministrationService(db)


def test_administrator_always_has_full_individual_and_aggregate_access(tmp_path, monkeypatch):
    svc = service(tmp_path)
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    for action in ("create", "read", "update", "delete", "assign", "review", "approve", "export", "publish", "aggregate"):
        decision = svc.evaluate_access_matrix(
            actor_id="admin", role_code="administrator", action=action,
            resource_type="sensitive_record", project_id="any", representation="individual"
        )
        assert decision.allowed
        assert decision.detail_visible
        assert decision.aggregate_allowed


def test_project_scoped_crud_and_aggregate_only_access(tmp_path, monkeypatch):
    svc = service(tmp_path)
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    svc.save_access_matrix(
        actor_id="admin", display_name="Leader project CRUD", principal_type="role",
        principal_id="project_manager", resource_type="task", project_id="project-a",
        data_scope="project", representation="individual",
        permissions={"create": True, "read": True, "update": True, "delete": True, "aggregate": True},
    )
    svc.save_access_matrix(
        actor_id="admin", display_name="Team aggregate only", principal_type="role",
        principal_id="reviewer", resource_type="workload", project_id="project-a",
        data_scope="project", representation="aggregated",
        permissions={"aggregate": True},
    )
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "researcher")
    leader = svc.evaluate_access_matrix(actor_id="lead", role_code="project_manager", action="update", resource_type="task", project_id="project-a")
    assert leader.allowed and leader.detail_visible
    outside = svc.evaluate_access_matrix(actor_id="lead", role_code="project_manager", action="update", resource_type="task", project_id="project-b")
    assert not outside.allowed
    aggregate = svc.evaluate_access_matrix(actor_id="review", role_code="reviewer", action="aggregate", resource_type="workload", project_id="project-a", representation="aggregated")
    assert aggregate.allowed and aggregate.aggregate_allowed and not aggregate.detail_visible
    detail = svc.evaluate_access_matrix(actor_id="review", role_code="reviewer", action="read", resource_type="workload", project_id="project-a", representation="individual")
    assert not detail.allowed and not detail.detail_visible


def test_access_matrix_change_is_audited(tmp_path, monkeypatch):
    svc = service(tmp_path)
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    rid = svc.save_access_matrix(
        actor_id="admin", display_name="User private notes", principal_type="user",
        principal_id="alice", resource_type="note", data_scope="user",
        representation="individual", permissions={"create": True, "read": True, "update": True},
    )
    rows = svc.list_domain("access_matrices")
    assert any(row["rule_id"] == rid for row in rows)
    assert any(event["entity_id"] == rid and event["event_type"] == "access.matrix.saved" for event in svc.audit_events())
