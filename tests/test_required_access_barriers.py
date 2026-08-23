from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
)
from natureai_next.server.required_access_barriers import RequiredAccessBarrierRepository


def test_new_required_asset_is_hidden_until_contract_exists(tmp_path) -> None:
    repository = RequiredAccessBarrierRepository(
        SqliteConnectionFactory(tmp_path / "access.sqlite3")
    )
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
    repository = RequiredAccessBarrierRepository(
        SqliteConnectionFactory(tmp_path / "access.sqlite3")
    )

    assert repository.allows_asset("legacy-asset", organization_id="org-a")


def test_required_collection_without_active_contract_hides_members(tmp_path) -> None:
    repository = RequiredAccessBarrierRepository(
        SqliteConnectionFactory(tmp_path / "access.sqlite3")
    )
    collection = ContractSubject(ContractSubjectKind.COLLECTION, "collection-1")
    repository.require_contract(collection, now_epoch=10)
    repository.link_collection_asset("collection-1", "asset-1")

    assert not repository.allows_asset("asset-1", organization_id="org-a")
