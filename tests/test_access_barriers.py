import pytest

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.server.access_barriers import AccessBarrierRepository
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
    restrict_contract,
    sharing_amendment,
)


def _repository(tmp_path):
    return AccessBarrierRepository(SqliteConnectionFactory(tmp_path / "access.sqlite3"))


def test_admin_can_replace_unrestricted_asset_with_organization_wall(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-1")
    unrestricted = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ALL),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="admin",
        contract_id="all-1",
        now_epoch=10,
    )
    narrowed = restrict_contract(
        ContractDraft(
            unrestricted.targets,
            "",
            False,
            0,
            subject=subject,
        ),
        subject=subject,
        replacement_targets=(
            AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),
        ),
        administrator=True,
    )
    active = repository.create(
        narrowed,
        requested_by="admin",
        replaces_contract_id=unrestricted.contract_id,
        contract_id="org-only",
        now_epoch=20,
    )

    assert active.status == "active"
    assert repository.contract("all-1").status == "superseded"
    assert repository.allows(subject, organization_id="org-a")
    assert not repository.allows(subject, organization_id="org-b")


def test_collection_contract_can_be_replaced_without_touching_assets(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.COLLECTION, "collection-1")
    first = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ALL),),
            "",
            False,
            0,
            subject=subject,
        ),
        requested_by="admin",
        contract_id="collection-all",
        now_epoch=10,
    )
    replacement = restrict_contract(
        ContractDraft(first.targets, "", False, 0, subject=subject),
        subject=subject,
        replacement_targets=(
            AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),
        ),
        administrator=True,
    )
    repository.create(
        replacement,
        requested_by="admin",
        replaces_contract_id=first.contract_id,
        contract_id="collection-org-a",
        now_epoch=20,
    )

    assert repository.current(subject).contract_id == "collection-org-a"
    assert repository.allows(subject, organization_id="org-a")
    assert not repository.allows(subject, organization_id="org-b")


def test_collection_wall_is_cumulative_with_asset_contract(tmp_path) -> None:
    repository = _repository(tmp_path)
    asset = ContractSubject(ContractSubjectKind.ASSET, "asset-cumulative")
    collection = ContractSubject(ContractSubjectKind.COLLECTION, "collection-restricted")
    repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ALL),),
            "",
            False,
            0,
            subject=asset,
        ),
        requested_by="admin",
        contract_id="asset-all",
        now_epoch=10,
    )
    repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),),
            "",
            False,
            0,
            subject=collection,
        ),
        requested_by="admin",
        contract_id="collection-org-a",
        now_epoch=11,
    )
    repository.link_collection_asset(collection.subject_id, asset.subject_id)

    assert repository.collections_for_asset(asset.subject_id) == (collection.subject_id,)
    assert repository.allows_asset(asset.subject_id, organization_id="org-a")
    assert not repository.allows_asset(asset.subject_id, organization_id="org-b")

    repository.unlink_collection_asset(collection.subject_id, asset.subject_id)
    assert repository.allows_asset(asset.subject_id, organization_id="org-b")


def test_project_sharing_stays_pending_until_same_owner_signs_twice(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-2")
    base = ContractDraft(
        (AccessTarget(AccessTargetKind.PROJECT, project_id="project-a"),),
        "",
        False,
        0,
        source_project_id="project-a",
        subject=subject,
    )
    current = repository.create(
        base,
        requested_by="member-a",
        contract_id="project-contract",
        now_epoch=10,
    )
    proposed = sharing_amendment(
        base,
        requested_targets=(
            AccessTarget(
                AccessTargetKind.ORGANIZATION_PROJECT,
                organization_id="org-b",
                project_id="project-b",
            ),
        ),
    )
    pending = repository.create(
        proposed,
        requested_by="member-a",
        replaces_contract_id=current.contract_id,
        contract_id="share-contract",
        now_epoch=20,
    )
    assert pending.status == "pending"
    assert repository.current(subject).contract_id == current.contract_id

    once = repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="sig-1",
        now_epoch=30,
    )
    assert once.status == "pending"
    twice = repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="sig-2",
        now_epoch=31,
    )
    assert twice.status == "active"
    assert repository.contract(current.contract_id).status == "superseded"
    assert repository.allows(
        subject,
        organization_id="org-b",
        project_ids=("project-b",),
    )


def test_second_signature_cannot_be_switched_to_another_owner(tmp_path) -> None:
    repository = _repository(tmp_path)
    subject = ContractSubject(ContractSubjectKind.ASSET, "asset-3")
    pending = repository.create(
        ContractDraft(
            (AccessTarget(AccessTargetKind.PROJECT, project_id="project-a"),),
            "",
            True,
            2,
            source_project_id="project-a",
            subject=subject,
        ),
        requested_by="member-a",
        contract_id="pending",
        now_epoch=10,
    )
    repository.sign(
        pending.contract_id,
        owner_identity="owner-a",
        signature_id="sig-1",
        now_epoch=20,
    )

    with pytest.raises(PermissionError):
        repository.sign(
            pending.contract_id,
            owner_identity="owner-b",
            signature_id="sig-2",
            now_epoch=21,
        )
