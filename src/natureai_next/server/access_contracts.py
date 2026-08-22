"""Governed data-access contracts and information-barrier defaults.

Intake scope is derived from the authenticated actor that introduces data. Widening
access is a contract amendment; it is never an implicit ACL side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IntakeActorKind(StrEnum):
    ADMIN = "admin"
    GLOBAL_SERVICE = "global_service"
    ORGANIZATION_SERVICE = "organization_service"
    USER = "user"
    CONTRACTED_CLIENT = "contracted_client"


class AccessTargetKind(StrEnum):
    ALL = "all"
    ORGANIZATION = "organization"
    PROJECT = "project"
    ORGANIZATION_PROJECT = "organization_project"


@dataclass(frozen=True, slots=True)
class AccessTarget:
    kind: AccessTargetKind
    organization_id: str = ""
    project_id: str = ""

    def __post_init__(self) -> None:
        if self.kind is AccessTargetKind.ALL:
            if self.organization_id or self.project_id:
                raise ValueError("all-access target cannot carry organization/project")
            return
        if self.kind is AccessTargetKind.ORGANIZATION:
            if not self.organization_id.strip() or self.project_id:
                raise ValueError("organization target requires only organization_id")
            return
        if self.kind is AccessTargetKind.PROJECT:
            if not self.project_id.strip() or self.organization_id:
                raise ValueError("project target requires only project_id")
            return
        if not self.organization_id.strip() or not self.project_id.strip():
            raise ValueError("organization-project target requires both identifiers")


@dataclass(frozen=True, slots=True)
class IntakeContext:
    actor_kind: IntakeActorKind
    actor_id: str
    organization_id: str = ""
    selected_project_id: str = ""
    project_memberships: tuple[str, ...] = ()
    existing_contract_id: str = ""


@dataclass(frozen=True, slots=True)
class ContractDraft:
    targets: tuple[AccessTarget, ...]
    inherited_contract_id: str
    requires_project_owner_approval: bool
    required_owner_signatures: int
    source_project_id: str = ""

    @property
    def unrestricted(self) -> bool:
        return self.targets == (AccessTarget(AccessTargetKind.ALL),)


def default_intake_contract(context: IntakeContext) -> ContractDraft:
    """Derive the non-interactive contract applied at ingest time."""
    if not context.actor_id.strip():
        raise ValueError("actor_id is required")
    if context.actor_kind in {IntakeActorKind.ADMIN, IntakeActorKind.GLOBAL_SERVICE}:
        return ContractDraft((AccessTarget(AccessTargetKind.ALL),), "", False, 0)
    if context.actor_kind is IntakeActorKind.ORGANIZATION_SERVICE:
        if not context.organization_id.strip():
            raise ValueError("organization service requires organization_id")
        return ContractDraft(
            (AccessTarget(AccessTargetKind.ORGANIZATION, context.organization_id.strip()),),
            "",
            False,
            0,
        )
    if context.actor_kind is IntakeActorKind.CONTRACTED_CLIENT:
        if not context.existing_contract_id.strip():
            raise ValueError("contracted client requires existing_contract_id")
        return ContractDraft((), context.existing_contract_id.strip(), False, 0)

    memberships = {value.strip() for value in context.project_memberships if value.strip()}
    selected = context.selected_project_id.strip()
    if memberships:
        if not selected:
            raise ValueError("project member must select the destination project")
        if selected not in memberships:
            raise PermissionError("selected project is not one of the user's memberships")
        return ContractDraft(
            (AccessTarget(AccessTargetKind.PROJECT, project_id=selected),),
            context.existing_contract_id.strip(),
            False,
            0,
            source_project_id=selected,
        )
    if context.existing_contract_id.strip():
        return ContractDraft((), context.existing_contract_id.strip(), False, 0)
    if not context.organization_id.strip():
        raise ValueError("uncontracted user intake requires organization_id")
    return ContractDraft(
        (AccessTarget(AccessTargetKind.ORGANIZATION, context.organization_id.strip()),),
        "",
        False,
        0,
    )


def sharing_amendment(
    base: ContractDraft,
    *,
    requested_targets: tuple[AccessTarget, ...],
    requested_by_project_owner: bool = False,
    administrator_batch: bool = False,
) -> ContractDraft:
    """Create a draft that widens access while preserving project-owner control.

    Standard user/supervisor choices are represented by targets for another project,
    the whole organization, another organization, or a specific project in another
    organization. Multiple targets are supported for administrative import scripts.
    """
    if not requested_targets:
        raise ValueError("at least one sharing target is required")
    if len(requested_targets) > 1 and not administrator_batch:
        raise PermissionError("multiple sharing targets require administrator batch mode")
    combined = _deduplicate(base.targets + requested_targets)
    project_governed = bool(base.source_project_id)
    if project_governed:
        # A project owner allowing broader sharing must make two explicit attestations.
        return ContractDraft(
            combined,
            base.inherited_contract_id,
            True,
            2,
            source_project_id=base.source_project_id,
        )
    return ContractDraft(
        combined,
        base.inherited_contract_id,
        False,
        0,
        source_project_id=base.source_project_id,
    )


def owner_approval_complete(
    draft: ContractDraft,
    *,
    owner_identity: str,
    signature_ids: tuple[str, ...],
) -> bool:
    if not draft.requires_project_owner_approval:
        return True
    if not owner_identity.strip():
        return False
    distinct = {value.strip() for value in signature_ids if value.strip()}
    return len(distinct) >= draft.required_owner_signatures


def _deduplicate(values: tuple[AccessTarget, ...]) -> tuple[AccessTarget, ...]:
    result: list[AccessTarget] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)
