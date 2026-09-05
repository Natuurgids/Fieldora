from __future__ import annotations

import os

import pytest

from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
)
from natureai_next.server.postgres_access import PostgresAccessControlRepository
from natureai_next.server.required_access_barriers import RequiredAccessBarrierRepository


@pytest.mark.integration
def test_postgres_contract_mutation_and_audit_chain_commit_together() -> None:
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    access = PostgresAccessControlRepository(lambda: psycopg.connect(dsn))
    repository = RequiredAccessBarrierRepository(access._factory)
    subject = ContractSubject(ContractSubjectKind.ASSET, "postgres-audited-asset")

    repository.require_contract(
        subject,
        actor_id="postgres-ingest-service",
        now_epoch=10,
    )
    contract = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="postgres-ingest-service",
        contract_id="postgres-audited-contract",
        now_epoch=11,
    )
    repository.assign_project_owner(
        "project-a",
        "owner-a",
        assigned_by="platform-admin",
        now_epoch=12,
    )

    assert contract.status == "active"
    assert repository.allows_asset(subject.subject_id, organization_id="org-a")
    assert not repository.allows_asset(subject.subject_id, organization_id="org-b")
    actions = {event["action"] for event in access.audit_events(50)}
    assert "data_contract.required" in actions
    assert "data_contract.activated" in actions
    assert "data_contract.project_owner_assigned" in actions
    verified, detail = access.verify_audit_chain()
    assert verified, detail
