from __future__ import annotations

from datetime import UTC, datetime

import pytest

from natureai_next.server.operator_control import (
    ServiceState,
    SqliteOperatorRepository,
    operator_snapshot,
)
from natureai_next.server.platform_extensions import ProjectOptionalStagedIngestionStore
from natureai_next.server.scientific_collaboration import SqliteCollaborationRepository
from natureai_next.server.service_trust import ServiceTrustAuthority


def test_projectless_staged_intake_is_first_class(tmp_path) -> None:
    store = ProjectOptionalStagedIngestionStore(
        tmp_path / "staging.sqlite3", tmp_path / "quarantine"
    )
    submission = store.create_submission(
        subject_id="citizen-1",
        organization_id="institute-a",
        purpose="research",
        publication_policy="review",
        expected_files=2,
    )

    assert submission.project_id == ""
    assert submission.organization_id == "institute-a"
    assert submission.state == "uploading"


def test_submission_and_review_do_not_require_project(tmp_path) -> None:
    repository = SqliteCollaborationRepository(tmp_path / "collaboration.sqlite3")
    submission = repository.create_submission(
        organization_id="institute-a",
        submitted_by="citizen-1",
        source_type="external-contributor",
        source_reference="field-form-42",
        collection_id="reference-images",
        purpose="research",
        now_epoch=100,
    )
    assert submission.project_id == ""

    case = repository.create_review_case(
        organization_id="institute-a",
        subject_type="asset",
        subject_id="asset-42",
        domain="taxonomy",
        specialty="Coleoptera",
        geography="Palearctic",
        requested_by="triage-1",
        now_epoch=101,
    )
    first = repository.add_determination(
        review_case_id=case.review_case_id,
        expert_id="expert-a",
        assertion="Carabidae",
        confidence=0.91,
        evidence_json={"method": "morphology"},
        now_epoch=102,
    )
    second = repository.add_determination(
        review_case_id=case.review_case_id,
        expert_id="expert-b",
        assertion="Carabus sp.",
        confidence=0.83,
        evidence_json={"method": "image-review"},
        supersedes_id=first.determination_id,
        now_epoch=103,
    )
    accepted = repository.accept_determination(case.review_case_id, second.determination_id)

    assert case.project_id == ""
    assert accepted.state == "accepted"
    assert accepted.accepted_determination_id == second.determination_id
    assert [item.assertion for item in repository.determinations(case.review_case_id)] == [
        "Carabidae",
        "Carabus sp.",
    ]


def test_operator_services_have_guarded_durable_lifecycle(tmp_path) -> None:
    repository = SqliteOperatorRepository(tmp_path / "operator.sqlite3")
    service = repository.enroll(
        organization_id="institute-a",
        service_id="worker-ai-01",
        name="AI worker 01",
        service_type="ai-worker",
        node_name="node-a",
        software_version="5.4.0",
        configuration_sha256="a" * 64,
        certificate_serial="1234",
        certificate_not_after_epoch=10_000,
        now_epoch=100,
    )
    assert service.state == ServiceState.ENROLLED.value
    assert repository.transition(
        service.service_id, ServiceState.ACTIVE, now_epoch=101
    ).state == "active"
    assert repository.transition(
        service.service_id, ServiceState.DRAINING, now_epoch=102
    ).state == "draining"
    assert repository.transition(
        service.service_id, ServiceState.STOPPED, now_epoch=103
    ).state == "stopped"
    revoked = repository.transition(
        service.service_id, ServiceState.REVOKED, now_epoch=104
    )
    assert revoked.revoked_at_epoch == 104
    with pytest.raises(PermissionError):
        repository.heartbeat(service.service_id, now_epoch=105)


def test_operator_snapshot_reports_capacity_and_certificate_state(tmp_path) -> None:
    repository = SqliteOperatorRepository(tmp_path / "operator.sqlite3")
    repository.enroll(
        organization_id="institute-a",
        service_id="api-01",
        name="API 01",
        service_type="api",
        node_name="node-a",
        software_version="5.4.0",
        configuration_sha256="b" * 64,
        certificate_serial="5678",
        certificate_not_after_epoch=150,
        now_epoch=100,
    )
    repository.transition("api-01", ServiceState.ACTIVE, now_epoch=101)
    snapshot = operator_snapshot(
        repository,
        "institute-a",
        storage_paths=(tmp_path,),
        heartbeat_stale_seconds=10,
        certificate_warning_seconds=100,
        now_epoch=120,
    )

    assert snapshot["service_counts"]["active"] == 1
    assert snapshot["stale_service_count"] == 1
    assert snapshot["expiring_certificate_count"] == 1
    assert snapshot["storage"][0]["total_bytes"] > 0


def test_service_certificate_renews_without_changing_service_identity(tmp_path) -> None:
    authority = ServiceTrustAuthority(tmp_path / "pki")
    authority.initialize()
    certificate = tmp_path / "pki" / "worker.pem"
    private_key = tmp_path / "pki" / "worker-key.pem"
    first = authority.issue(
        service_id="worker-01",
        organization_id="institute-a",
        common_name="fieldora",
        certificate_path=certificate,
        private_key_path=private_key,
        dns_names=("worker-01",),
        lifetime_hours=24,
    )
    first_key = private_key.read_bytes()
    second = authority.issue(
        service_id="worker-01",
        organization_id="institute-a",
        common_name="fieldora",
        certificate_path=certificate,
        private_key_path=private_key,
        dns_names=("worker-01",),
        lifetime_hours=24,
    )
    inspected = authority.inspect(certificate)

    assert first.service_id == second.service_id == inspected.service_id == "worker-01"
    assert first.serial_number != second.serial_number
    assert private_key.read_bytes() == first_key
    assert datetime.fromisoformat(second.not_after_utc).astimezone(UTC) > datetime.now(UTC)
