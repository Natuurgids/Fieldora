import pytest

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
)
from natureai_next.server.required_access_barriers import RequiredAccessBarrierRepository


def _repository(tmp_path):
    return RequiredAccessBarrierRepository(
        SqliteConnectionFactory(tmp_path / "access.sqlite3")
    )


def test_new_required_asset_is_hidden_until_contract_exists(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "new-asset")
    repository.require_contract(subject, now_epoch=10)

    assert repository.contract_required(subject)
    assert not repository.allows_asset("new-asset", organization_id="org-a")

    repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="uploader",
        now_epoch=11,
    )

    assert repository.allows_asset("new-asset", organization_id="org-a")
    assert not repository.allows_asset("new-asset", organization_id="org-b")


def test_legacy_unmarked_asset_remains_pbac_only_for_migration(tmp_path) -> None:
    repository = _repository(tmp_path)

    assert repository.allows_asset("legacy-asset", organization_id="org-a")


def test_required_collection_without_active_contract_hides_members(tmp_path) -> None:
    repository = _repository(tmp_path)
    collection = ContractSubject(ContractSubjectKind.COLLECTION, "collection-1")
    repository.require_contract(collection, now_epoch=10)
    repository.link_collection_asset("collection-1", "asset-1")

    assert not repository.allows_asset("asset-1", organization_id="org-a")


def test_project_sharing_requires_recorded_source_owner_to_sign_twice(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-1")
    current = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.PROJECT, project_id="source-project"),),
            "",
            False,
            0,
            source_project_id="source-project",
            subject=subject,
        ),
        requested_by="member-a",
        contract_id="source-contract",
        now_epoch=10,
    )
    pending = repository.create(
        ContractDraft(
            (
                AccessTarget(AccessTargetKind.PROJECT, project_id="source-project"),
                AccessTarget(
                    AccessTargetKind.ORGANIZATION_PROJECT,
                    organization_id="recipient-org",
                    project_id="recipient-project",
                ),
            ),
            "",
            True,
            2,
            source_project_id="source-project",
            subject=subject,
        ),
        requested_by="member-a",
        replaces_contract_id=current.contract_id,
        contract_id="shared-contract",
        now_epoch=20,
    )
    repository.assign_project_owner(
        "source-project",
        "owner-a",
        assigned_by="platform-admin",
        now_epoch=21,
    )

    with pytest.raises(PermissionError):
        repository.sign(
            pending.contract_id,
            owner_identity="not-owner",
            signature_id="bad-signature",
            now_epoch=22,
        )

    first = repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="owner-attestation-1",
        now_epoch=23,
    )
    assert first.status == "pending"
    second = repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="owner-attestation-2",
        now_epoch=24,
    )
    assert second.status == "active"
    assert repository.project_owner("source-project").owner_identity == "owner-a"


def test_evidence_owner_contract_blocks_project_owner_from_widening(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-blocked")
    current = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.PROJECT, project_id="source-project"),),
            "",
            False,
            0,
            source_project_id="source-project",
            subject=subject,
        ),
        requested_by="evidence-owner",
        contract_id="source-contract",
        now_epoch=10,
    )
    repository.set_evidence_owner_contract(
        subject,
        "evidence-owner",
        (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="source-org"),),
        assigned_by="platform-admin",
        now_epoch=11,
    )
    pending = repository.create(
        ContractDraft(
            (
                AccessTarget(AccessTargetKind.PROJECT, project_id="source-project"),
                AccessTarget(
                    AccessTargetKind.ORGANIZATION_PROJECT,
                    organization_id="recipient-org",
                    project_id="recipient-project",
                ),
            ),
            "",
            True,
            2,
            source_project_id="source-project",
            subject=subject,
        ),
        requested_by="member-a",
        replaces_contract_id=current.contract_id,
        contract_id="blocked-share",
        now_epoch=20,
    )
    repository.assign_project_owner(
        "source-project",
        "project-owner",
        assigned_by="platform-admin",
        now_epoch=21,
    )

    assert not repository.project_share_allowed_by_evidence_owner(
        subject,
        pending.targets,
    )
    with pytest.raises(PermissionError, match="evidence owner contract blocks"):
        repository.sign(
            pending.contract_id,
            owner_identity="project-owner",
            signature_id="attestation-1",
            now_epoch=22,
        )
    assert not repository.allows_asset(
        subject.subject_id,
        organization_id="recipient-org",
        project_ids=("recipient-project",),
    )


def test_project_owner_can_share_within_evidence_owner_ceiling(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-allowed")
    repository.set_evidence_owner_contract(
        subject,
        "evidence-owner",
        (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="recipient-org"),),
        assigned_by="platform-admin",
        now_epoch=10,
    )

    assert repository.project_share_allowed_by_evidence_owner(
        subject,
        (
            AccessTarget(
                AccessTargetKind.ORGANIZATION_PROJECT,
                organization_id="recipient-org",
                project_id="recipient-project",
            ),
        ),
    )
    assert not repository.project_share_allowed_by_evidence_owner(
        subject,
        (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="other-org"),),
    )


def test_collection_evidence_owner_ceiling_prevents_member_asset_widening(tmp_path) -> None:
    repository = _repository(tmp_path)
    asset = ContractSubject(ContractSubjectKind.ASSET, "asset-in-collection")
    collection = ContractSubject(ContractSubjectKind.COLLECTION, "restricted-collection")
    repository.link_collection_asset(collection.subject_id, asset.subject_id)
    repository.set_evidence_owner_contract(
        collection,
        "collection-evidence-owner",
        (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="source-org"),),
        assigned_by="platform-admin",
        now_epoch=10,
    )

    assert not repository.project_share_allowed_by_evidence_owner(
        asset,
        (
            AccessTarget(
                AccessTargetKind.ORGANIZATION_PROJECT,
                organization_id="recipient-org",
                project_id="recipient-project",
            ),
        ),
    )
    assert repository.project_share_allowed_by_evidence_owner(
        asset,
        (
            AccessTarget(
                AccessTargetKind.ORGANIZATION_PROJECT,
                organization_id="source-org",
                project_id="source-project",
            ),
        ),
    )
