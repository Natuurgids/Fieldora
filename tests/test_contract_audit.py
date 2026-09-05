import sqlite3

import pytest

from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.access_barriers import AccessBarrierRepository
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
    sharing_amendment,
)
from natureai_next.server.required_access_barriers import RequiredAccessBarrierRepository


def _access(tmp_path):
    return SqliteAccessControlRepository(tmp_path / "access.sqlite3")


def _assert_audit_chain_verified(access) -> None:
    verified, detail = access.verify_audit_chain()
    assert verified, detail


def test_contract_creation_and_replacement_are_sealed_in_audit_chain(tmp_path) -> None:
    access = _access(tmp_path)
    repository = AccessBarrierRepository(access._factory)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-a")
    first = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ALL),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="admin",
        contract_id="contract-all",
        now_epoch=10,
    )
    repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="admin",
        replaces_contract_id=first.contract_id,
        contract_id="contract-org-a",
        now_epoch=20,
    )

    events = access.audit_events(20)
    actions = [event["action"] for event in events]
    assert "data_contract.activated" in actions
    assert "data_contract.superseded" in actions
    _assert_audit_chain_verified(access)


def test_double_attestation_and_activation_are_audited(tmp_path) -> None:
    access = _access(tmp_path)
    repository = AccessBarrierRepository(access._factory)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-share")
    base = ContractDraft(
        (AccessTarget(AccessTargetKind.PROJECT, project_id="source-project"),),
        "",
        False,
        0,
        source_project_id="source-project",
        subject=subject,
    )
    current = repository.create(
        base,
        requested_by="member-a",
        contract_id="base-contract",
        now_epoch=10,
    )
    pending = repository.create(
        sharing_amendment(
            base,
            requested_targets=(
                AccessTarget(
                    AccessTargetKind.ORGANIZATION_PROJECT,
                    organization_id="org-b",
                    project_id="project-b",
                ),
            ),
        ),
        requested_by="member-a",
        replaces_contract_id=current.contract_id,
        contract_id="share-contract",
        now_epoch=20,
    )
    repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="attestation-1",
        now_epoch=30,
    )
    repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="attestation-2",
        now_epoch=31,
    )

    events = access.audit_events(50)
    attested = [event for event in events if event["action"] == "data_contract.attested"]
    assert len(attested) == 2
    assert any(event["action"] == "data_contract.activated" for event in events)
    _assert_audit_chain_verified(access)


def test_owner_governance_changes_are_audited(tmp_path) -> None:
    access = _access(tmp_path)
    repository = RequiredAccessBarrierRepository(access._factory)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-owner")
    repository.require_contract(subject, actor_id="ingest-service", now_epoch=10)
    repository.assign_project_owner(
        "project-a", "owner-a", assigned_by="platform-admin", now_epoch=11
    )
    repository.set_evidence_owner_contract(
        subject,
        "evidence-owner",
        (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),),
        assigned_by="platform-admin",
        now_epoch=12,
    )

    actions = {event["action"] for event in access.audit_events(50)}
    assert "data_contract.required" in actions
    assert "data_contract.project_owner_assigned" in actions
    assert "data_contract.evidence_owner_ceiling_set" in actions
    _assert_audit_chain_verified(access)


def test_contract_mutation_rolls_back_when_audit_chain_cannot_be_sealed(tmp_path) -> None:
    access = _access(tmp_path)
    repository = AccessBarrierRepository(access._factory)
    connection = sqlite3.connect(tmp_path / "access.sqlite3")
    try:
        connection.execute("DROP TABLE access_audit_chain")
        connection.commit()
    finally:
        connection.close()

    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-no-audit")
    with pytest.raises(Exception):
        repository.create(
            ContractDraft(
                (AccessTarget(AccessTargetKind.ALL),),
                "",
                False,
                0,
                subject=subject,
            ),
            requested_by="admin",
            contract_id="must-not-commit",
            now_epoch=20,
        )

    connection = sqlite3.connect(tmp_path / "access.sqlite3")
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM access_data_contracts WHERE contract_id=?",
            ("must-not-commit",),
        ).fetchone()[0]
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM access_audit_events WHERE resource_id=?",
            ("must-not-commit",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 0
    assert audit_count == 0
