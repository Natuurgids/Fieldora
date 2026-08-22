"""Central PBAC decisions and local identity/contract administration."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import uuid4

from natureai_next.domain.access_control import (
    AccessDecision,
    AccessRequest,
    Contract,
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)

_PROJECT_CONTRACT_RIGHTS = {
    "view": (("project", "dossier"), "research"),
    "search": (("project", "dossier"), "research"),
    "export": (("project",), "research"),
    "view_job": (("job",), "administration"),
    "download_export": (("project_export",), "research"),
    "upload": (("asset",), "research"),
}


class AccessDenied(PermissionError):
    pass


class PolicyDecisionService:
    """Default-deny PBAC with role, attribute, contract, and object policy inputs."""

    def __init__(self, repository: SqliteAccessControlRepository) -> None:
        self._repository = repository

    def decide(self, request: AccessRequest) -> AccessDecision:
        at_utc = request.effective_time()
        identity = next(
            (
                item for item in self._repository.identities()
                if item.identity_id == request.subject_id
            ),
            None,
        )
        if identity is None or not identity.enabled:
            return self._record(request, AccessDecision(False, "unknown or disabled identity"))
        if (
            request.organization_id
            and identity.organization_id
            and identity.organization_id != request.organization_id
            and identity.attributes.get("platform_admin") != "true"
        ):
            return self._record(request, AccessDecision(False, "organization boundary"))
        role_ids = set(
            self._repository.role_ids(
                request.subject_id, request.organization_id, request.project_id
            )
        )
        matches: list[Policy] = []
        for policy in self._repository.policies():
            if self._matches(policy, request, role_ids, at_utc):
                matches.append(policy)
        denies = [item for item in matches if item.effect is PolicyEffect.DENY]
        if denies:
            return self._record(
                request,
                AccessDecision(
                    False, f"explicit deny: {denies[0].name}",
                    tuple(item.policy_id for item in denies),
                ),
            )
        allows = [item for item in matches if item.effect is PolicyEffect.ALLOW]
        if not allows:
            return self._record(request, AccessDecision(False, "default deny"))
        fields = request.fields
        return self._record(
            request,
            AccessDecision(
                True, f"allowed by {allows[0].name}",
                tuple(item.policy_id for item in allows),
                fields,
            ),
        )

    def require(self, request: AccessRequest) -> AccessDecision:
        decision = self.decide(request)
        if not decision.allowed:
            raise AccessDenied(decision.reason)
        return decision

    def _matches(
        self,
        policy: Policy,
        request: AccessRequest,
        role_ids: set[str],
        at_utc: str,
    ) -> bool:
        if not policy.enabled:
            return False
        if policy.subject_id and policy.subject_id != request.subject_id:
            return False
        if policy.role_id and policy.role_id not in role_ids:
            return False
        if not policy.subject_id and not policy.role_id:
            return False
        if request.action not in policy.actions and "*" not in policy.actions:
            return False
        if (
            request.resource_type not in policy.resource_types
            and "*" not in policy.resource_types
        ):
            return False
        if policy.resource_id and policy.resource_id != request.resource_id:
            return False
        if policy.organization_id and policy.organization_id != request.organization_id:
            return False
        if policy.project_id and policy.project_id != request.project_id:
            return False
        if policy.purposes and request.purpose not in policy.purposes:
            return False
        if policy.fields and not set(request.fields).issubset(policy.fields):
            return False
        if policy.valid_from_utc and at_utc < policy.valid_from_utc:
            return False
        if policy.valid_until_utc and at_utc >= policy.valid_until_utc:
            return False
        if any(
            request.attributes.get(key) != value
            for key, value in policy.conditions.items()
        ):
            return False
        if policy.source is PolicySource.CONTRACT:
            contract = self._repository.contract(policy.source_id)
            if contract is None or not contract.active_at(at_utc):
                return False
        return True

    def _record(
        self, request: AccessRequest, decision: AccessDecision
    ) -> AccessDecision:
        self._repository.append_audit(
            {
                "occurred_at_utc": datetime.now(UTC).isoformat(),
                "subject_id": request.subject_id,
                "action": request.action,
                "resource_type": request.resource_type,
                "resource_id": request.resource_id,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "policy_ids": decision.matched_policy_ids,
                "request": asdict(request),
            }
        )
        return decision


class AccessAdministrationService:
    def __init__(self, repository: SqliteAccessControlRepository) -> None:
        self.repository = repository

    def create_identity(
        self, display_name: str, organization_id: str, kind: IdentityKind
    ) -> Identity:
        identity = Identity(
            str(uuid4()), kind, display_name.strip(), organization_id.strip()
        )
        self.repository.put_identity(identity)
        return identity

    def create_organization(self, organization_id: str, name: str) -> Organization:
        organization = Organization(organization_id.strip(), name.strip())
        self.repository.put_organization(organization)
        return organization

    def add_group_member(self, group_id: str, member_id: str) -> None:
        self.repository.add_group_member(group_id.strip(), member_id.strip())

    def create_contract(
        self,
        title: str,
        organization_id: str,
        starts_at_utc: str,
        ends_at_utc: str,
    ) -> Contract:
        contract = Contract(
            str(uuid4()), title.strip(), organization_id.strip(),
            starts_at_utc.strip(), ends_at_utc.strip(), "active", {},
        )
        self.repository.put_contract(contract)
        return contract

    def create_project_contract_grant(
        self,
        *,
        title: str,
        organization_id: str,
        project_id: str,
        subject_id: str,
        starts_at_utc: str,
        ends_at_utc: str,
        rights: tuple[str, ...],
    ) -> tuple[Contract, tuple[Policy, ...]]:
        (
            title, organization_id, project_id, subject_id,
            start, end, normalized_rights,
        ) = self._validate_project_contract(
            title, organization_id, project_id, subject_id,
            starts_at_utc, ends_at_utc, rights,
        )
        contract = Contract(
            str(uuid4()), title, organization_id,
            start.isoformat(), end.isoformat(), "active",
            {
                "grant_type": "project_access",
                "project_id": project_id,
                "subject_id": subject_id,
                "rights": list(normalized_rights),
            },
        )
        policies = self._project_contract_policies(contract)
        self.repository.put_contract_with_policies(contract, policies)
        return contract, policies

    def propose_project_contract_grant(
        self,
        *,
        requested_by: str,
        required_approvals: int = 1,
        title: str,
        organization_id: str,
        project_id: str,
        subject_id: str,
        starts_at_utc: str,
        ends_at_utc: str,
        rights: tuple[str, ...],
    ) -> Contract:
        (
            title, organization_id, project_id, subject_id,
            start, end, normalized_rights,
        ) = self._validate_project_contract(
            title, organization_id, project_id, subject_id,
            starts_at_utc, ends_at_utc, rights,
        )
        requester = self.repository.identity(requested_by.strip())
        if requester is None or requester.organization_id != organization_id:
            raise ValueError("contract requester must belong to its organization")
        if (
            isinstance(required_approvals, bool)
            or not isinstance(required_approvals, int)
            or not 1 <= required_approvals <= 10
        ):
            raise ValueError("required approvals must be between 1 and 10")
        contract = Contract(
            str(uuid4()), title, organization_id, start.isoformat(), end.isoformat(),
            "proposed",
            {
                "grant_type": "project_access",
                "project_id": project_id,
                "subject_id": subject_id,
                "rights": list(normalized_rights),
                "approval_required": True,
                "required_approvals": required_approvals,
                "approvals": [],
                "requested_by": requester.identity_id,
                "requested_at_utc": datetime.now(UTC).isoformat(),
            },
        )
        self.repository.put_contract(contract)
        return contract

    def approve_project_contract_grant(
        self, contract_id: str, approved_by: str
    ) -> tuple[Contract, tuple[Policy, ...]]:
        contract = self.repository.contract(contract_id.strip())
        approver = self.repository.identity(approved_by.strip())
        if contract is None or contract.status != "proposed":
            raise ValueError("contract is not awaiting approval")
        if (
            approver is None
            or not approver.enabled
            or approver.organization_id != contract.organization_id
            or approved_by == contract.terms.get("requested_by")
        ):
            raise ValueError("contract requires a different organizational approver")
        approvals = list(contract.terms.get("approvals", []))
        if any(item.get("approved_by") == approver.identity_id for item in approvals):
            raise ValueError("identity has already approved this contract")
        approval = {
            "approved_by": approver.identity_id,
            "approved_at_utc": datetime.now(UTC).isoformat(),
        }
        approvals.append(approval)
        required_approvals = int(contract.terms.get("required_approvals", 1))
        activated = len(approvals) >= required_approvals
        terms = {
            **contract.terms,
            "approvals": approvals,
            "approval_count": len(approvals),
        }
        if activated:
            # Preserve the 0.08.18 fields for consumers that only understand a
            # single independent approval.
            terms.update(approval)
        updated = replace(
            contract,
            status="active" if activated else "proposed",
            terms=terms,
        )
        policies = self._project_contract_policies(updated) if activated else ()
        if activated:
            saved = self.repository.put_contract_with_policies(
                updated, policies, expected=contract
            )
        else:
            saved = self.repository.replace_contract_if_current(updated, contract)
        if not saved:
            raise ValueError("contract approvals changed concurrently")
        return updated, policies

    def _project_contract_policies(
        self, contract: Contract
    ) -> tuple[Policy, ...]:
        subject_id = str(contract.terms["subject_id"])
        project_id = str(contract.terms["project_id"])
        return tuple(
            Policy(
                policy_id=str(uuid4()),
                name=f"{contract.title}: {right}",
                effect=PolicyEffect.ALLOW,
                source=PolicySource.CONTRACT,
                source_id=contract.contract_id,
                subject_id=subject_id,
                role_id="",
                actions=(right,),
                resource_types=_PROJECT_CONTRACT_RIGHTS[right][0],
                organization_id=contract.organization_id,
                project_id=project_id,
                purposes=(_PROJECT_CONTRACT_RIGHTS[right][1],),
                valid_until_utc=contract.ends_at_utc,
            )
            for right in contract.terms["rights"]
        )

    def _validate_project_contract(
        self,
        title: str,
        organization_id: str,
        project_id: str,
        subject_id: str,
        starts_at_utc: str,
        ends_at_utc: str,
        rights: tuple[str, ...],
    ):
        title = title.strip()
        organization_id = organization_id.strip()
        project_id = project_id.strip()
        subject_id = subject_id.strip()
        normalized_rights = tuple(dict.fromkeys(item.strip() for item in rights))
        if not title or not project_id or not normalized_rights or any(
            item not in _PROJECT_CONTRACT_RIGHTS for item in normalized_rights
        ):
            raise ValueError("invalid project contract rights")
        identity = self.repository.identity(subject_id)
        if identity is None or identity.organization_id != organization_id:
            raise ValueError("contract subject must belong to its organization")
        start = datetime.fromisoformat(starts_at_utc)
        end = datetime.fromisoformat(ends_at_utc)
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("contract dates must be timezone-aware and ordered")
        return (
            title, organization_id, project_id, subject_id,
            start.astimezone(UTC), end.astimezone(UTC), normalized_rights,
        )

    def set_contract_status(self, contract_id: str, status: str) -> Contract:
        if status not in ("active", "suspended", "terminated"):
            raise ValueError("invalid contract status")
        contract = self.repository.contract(contract_id.strip())
        if contract is None:
            raise KeyError(contract_id)
        if (
            status == "active"
            and contract.terms.get("approval_required")
            and not contract.terms.get("approved_by")
        ):
            raise ValueError("contract requires independent approval")
        if contract.status == "proposed" and status != "terminated":
            raise ValueError("proposed contracts require independent approval")
        updated = replace(contract, status=status)
        self.repository.put_contract(updated)
        return updated

    def grant_role(
        self, subject_id: str, role_id: str, organization_id: str, project_id: str = ""
    ) -> None:
        self.repository.assign_role(subject_id, role_id, organization_id, project_id)

    def create_policy(
        self,
        *,
        name: str,
        effect: PolicyEffect,
        source: PolicySource,
        source_id: str = "",
        subject_id: str = "",
        role_id: str = "",
        actions: tuple[str, ...],
        resource_types: tuple[str, ...],
        resource_id: str = "",
        organization_id: str = "",
        project_id: str = "",
        purposes: tuple[str, ...] = (),
        fields: tuple[str, ...] = (),
        valid_until_utc: str = "",
    ) -> Policy:
        policy = Policy(
            policy_id=str(uuid4()), name=name.strip(), effect=effect, source=source,
            source_id=source_id, subject_id=subject_id, role_id=role_id,
            actions=actions, resource_types=resource_types,
            resource_id=resource_id,
            organization_id=organization_id, project_id=project_id,
            purposes=purposes, fields=fields, valid_until_utc=valid_until_utc,
        )
        self.repository.put_policy(policy)
        return policy
