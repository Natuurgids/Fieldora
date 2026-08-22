import pytest

from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    IntakeActorKind,
    IntakeContext,
    default_intake_contract,
    owner_approval_complete,
    sharing_amendment,
)


def test_admin_and_global_service_imports_are_unrestricted() -> None:
    for kind in (IntakeActorKind.ADMIN, IntakeActorKind.GLOBAL_SERVICE):
        draft = default_intake_contract(IntakeContext(kind, "actor-1"))
        assert draft.unrestricted
        assert not draft.requires_project_owner_approval


def test_organization_service_is_restricted_to_its_organization() -> None:
    draft = default_intake_contract(
        IntakeContext(
            IntakeActorKind.ORGANIZATION_SERVICE,
            "org-ingest",
            organization_id="org-a",
        )
    )
    assert draft.targets == (
        AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),
    )


def test_contracted_phone_or_client_inherits_contract() -> None:
    draft = default_intake_contract(
        IntakeContext(
            IntakeActorKind.CONTRACTED_CLIENT,
            "phone-42",
            organization_id="org-a",
            existing_contract_id="contract-123",
        )
    )
    assert draft.targets == ()
    assert draft.inherited_contract_id == "contract-123"


def test_project_member_must_select_one_of_their_projects() -> None:
    with pytest.raises(ValueError):
        default_intake_contract(
            IntakeContext(
                IntakeActorKind.USER,
                "user-a",
                organization_id="org-a",
                project_memberships=("project-a", "project-b"),
            )
        )
    with pytest.raises(PermissionError):
        default_intake_contract(
            IntakeContext(
                IntakeActorKind.USER,
                "user-a",
                organization_id="org-a",
                selected_project_id="project-z",
                project_memberships=("project-a", "project-b"),
            )
        )

    draft = default_intake_contract(
        IntakeContext(
            IntakeActorKind.USER,
            "user-a",
            organization_id="org-a",
            selected_project_id="project-b",
            project_memberships=("project-a", "project-b"),
        )
    )
    assert draft.targets == (
        AccessTarget(AccessTargetKind.PROJECT, project_id="project-b"),
    )
    assert draft.source_project_id == "project-b"


def test_project_sharing_requires_owner_double_attestation() -> None:
    base = default_intake_contract(
        IntakeContext(
            IntakeActorKind.USER,
            "user-a",
            organization_id="org-a",
            selected_project_id="project-a",
            project_memberships=("project-a",),
        )
    )
    shared = sharing_amendment(
        base,
        requested_targets=(
            AccessTarget(
                AccessTargetKind.ORGANIZATION_PROJECT,
                organization_id="org-b",
                project_id="project-b",
            ),
        ),
    )
    assert shared.requires_project_owner_approval
    assert shared.required_owner_signatures == 2
    assert not owner_approval_complete(
        shared, owner_identity="owner-a", signature_ids=("sig-1",)
    )
    assert owner_approval_complete(
        shared, owner_identity="owner-a", signature_ids=("sig-1", "sig-2")
    )


def test_multiple_cross_wall_targets_are_reserved_for_admin_batch_contracts() -> None:
    base = default_intake_contract(
        IntakeContext(
            IntakeActorKind.ADMIN,
            "admin-a",
        )
    )
    targets = (
        AccessTarget(AccessTargetKind.ORGANIZATION, organization_id="org-a"),
        AccessTarget(
            AccessTargetKind.ORGANIZATION_PROJECT,
            organization_id="org-b",
            project_id="project-x",
        ),
    )
    with pytest.raises(PermissionError):
        sharing_amendment(base, requested_targets=targets)
    draft = sharing_amendment(base, requested_targets=targets, administrator_batch=True)
    assert len(draft.targets) == 3  # unrestricted base plus both explicit targets
