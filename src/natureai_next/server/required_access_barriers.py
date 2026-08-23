"""Fail-closed and precedence rules for governed evidence contracts.

New evidence is contract-required. Project-governed sharing requires the persisted source
project owner to attest twice, but that owner may never widen access beyond a stricter
upstream evidence-owner contract. Evidence provenance/ownership never moves to recipients.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from natureai_next.server.access_barriers import AccessBarrierRepository
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractSubject,
    ContractSubjectKind,
)


@dataclass(frozen=True, slots=True)
class ProjectContractOwner:
    project_id: str
    owner_identity: str
    assigned_by: str
    assigned_at_epoch: int


@dataclass(frozen=True, slots=True)
class EvidenceOwnerContract:
    subject_kind: str
    subject_id: str
    owner_identity: str
    targets: tuple[AccessTarget, ...]
    assigned_by: str
    assigned_at_epoch: int


class RequiredAccessBarrierRepository(AccessBarrierRepository):
    def __init__(self, factory) -> None:
        super().__init__(factory)
        connection = factory.connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS access_contract_requirements(
                    subject_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    required_since_epoch BIGINT NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY(subject_kind,subject_id)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS access_project_contract_owners(
                    project_id TEXT PRIMARY KEY,
                    owner_identity TEXT NOT NULL,
                    assigned_by TEXT NOT NULL,
                    assigned_at_epoch BIGINT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS access_evidence_owner_contracts(
                    subject_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    owner_identity TEXT NOT NULL,
                    targets_json TEXT NOT NULL,
                    assigned_by TEXT NOT NULL,
                    assigned_at_epoch BIGINT NOT NULL,
                    PRIMARY KEY(subject_kind,subject_id)
                )"""
            )
        finally:
            connection.close()

    def require_contract(
        self,
        subject: ContractSubject,
        *,
        reason: str = "governed_intake",
        now_epoch: int | None = None,
    ) -> None:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_contract_requirements VALUES(?,?,?,?) "
                "ON CONFLICT(subject_kind,subject_id) DO NOTHING",
                (subject.kind.value, subject.subject_id, now, reason[:200]),
            )
        finally:
            connection.close()

    def contract_required(self, subject: ContractSubject) -> bool:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT 1 FROM access_contract_requirements "
                "WHERE subject_kind=? AND subject_id=? LIMIT 1",
                (subject.kind.value, subject.subject_id),
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def assign_project_owner(
        self,
        project_id: str,
        owner_identity: str,
        *,
        assigned_by: str,
        now_epoch: int | None = None,
    ) -> ProjectContractOwner:
        project = project_id.strip()
        owner = owner_identity.strip()
        actor = assigned_by.strip()
        if not project or not owner or not actor:
            raise ValueError("project, owner identity and assigning identity are required")
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_project_contract_owners VALUES(?,?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "owner_identity=excluded.owner_identity,"
                "assigned_by=excluded.assigned_by,"
                "assigned_at_epoch=excluded.assigned_at_epoch",
                (project, owner, actor, now),
            )
        finally:
            connection.close()
        result = self.project_owner(project)
        assert result is not None
        return result

    def project_owner(self, project_id: str) -> ProjectContractOwner | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT project_id,owner_identity,assigned_by,assigned_at_epoch "
                "FROM access_project_contract_owners WHERE project_id=?",
                (project_id.strip(),),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else ProjectContractOwner(*row)

    def set_evidence_owner_contract(
        self,
        subject: ContractSubject,
        owner_identity: str,
        targets: tuple[AccessTarget, ...],
        *,
        assigned_by: str,
        now_epoch: int | None = None,
    ) -> EvidenceOwnerContract:
        owner = owner_identity.strip()
        actor = assigned_by.strip()
        if not owner or not actor or not targets:
            raise ValueError("evidence owner, assigning identity and targets are required")
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        payload = json.dumps(
            [
                {
                    "kind": target.kind.value,
                    "organization_id": target.organization_id,
                    "project_id": target.project_id,
                }
                for target in targets
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_evidence_owner_contracts VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(subject_kind,subject_id) DO UPDATE SET "
                "owner_identity=excluded.owner_identity,targets_json=excluded.targets_json,"
                "assigned_by=excluded.assigned_by,assigned_at_epoch=excluded.assigned_at_epoch",
                (subject.kind.value, subject.subject_id, owner, payload, actor, now),
            )
        finally:
            connection.close()
        result = self.evidence_owner_contract(subject)
        assert result is not None
        return result

    def evidence_owner_contract(
        self, subject: ContractSubject
    ) -> EvidenceOwnerContract | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT subject_kind,subject_id,owner_identity,targets_json,"
                "assigned_by,assigned_at_epoch FROM access_evidence_owner_contracts "
                "WHERE subject_kind=? AND subject_id=?",
                (subject.kind.value, subject.subject_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        raw = json.loads(str(row[3]))
        targets = tuple(
            AccessTarget(
                AccessTargetKind(str(item["kind"])),
                organization_id=str(item.get("organization_id", "")),
                project_id=str(item.get("project_id", "")),
            )
            for item in raw
        )
        return EvidenceOwnerContract(
            str(row[0]), str(row[1]), str(row[2]), targets, str(row[4]), int(row[5])
        )

    def project_share_allowed_by_evidence_owner(
        self,
        subject: ContractSubject,
        requested_targets: tuple[AccessTarget, ...],
    ) -> bool:
        owner_contract = self.evidence_owner_contract(subject)
        if owner_contract is None:
            return True
        return all(
            any(_target_contains(ceiling, requested) for ceiling in owner_contract.targets)
            for requested in requested_targets
        )

    def sign(
        self,
        contract_id: str,
        *,
        owner_identity: str,
        signature_id: str,
        now_epoch: int | None = None,
    ):
        contract = self.contract(contract_id)
        if contract is None:
            raise KeyError(contract_id)
        if contract.source_project_id:
            owner = self.project_owner(contract.source_project_id)
            if owner is None or owner.owner_identity != owner_identity.strip():
                raise PermissionError("only the recorded source project owner may attest")
            if not self.project_share_allowed_by_evidence_owner(
                contract.subject, contract.targets
            ):
                raise PermissionError("evidence owner contract blocks this project sharing")
        return super().sign(
            contract_id,
            owner_identity=owner_identity,
            signature_id=signature_id,
            now_epoch=now_epoch,
        )

    def allows(
        self,
        subject: ContractSubject,
        *,
        organization_id: str,
        project_ids: tuple[str, ...] = (),
    ) -> bool:
        if self.contract_required(subject) and self.current(subject) is None:
            return False
        owner_contract = self.evidence_owner_contract(subject)
        if owner_contract is not None and not _targets_allow(
            owner_contract.targets,
            organization_id=organization_id,
            project_ids=project_ids,
        ):
            return False
        return super().allows(
            subject,
            organization_id=organization_id,
            project_ids=project_ids,
        )

    def allows_asset(
        self,
        asset_id: str,
        *,
        organization_id: str,
        project_ids: tuple[str, ...] = (),
    ) -> bool:
        subjects = [ContractSubject(ContractSubjectKind.ASSET, asset_id)]
        subjects.extend(
            ContractSubject(ContractSubjectKind.COLLECTION, collection_id)
            for collection_id in self.collections_for_asset(asset_id)
        )
        for subject in subjects:
            if self.contract_required(subject) and self.current(subject) is None:
                return False
            owner_contract = self.evidence_owner_contract(subject)
            if owner_contract is not None and not _targets_allow(
                owner_contract.targets,
                organization_id=organization_id,
                project_ids=project_ids,
            ):
                return False
        return super().allows_asset(
            asset_id,
            organization_id=organization_id,
            project_ids=project_ids,
        )


def _targets_allow(
    targets: tuple[AccessTarget, ...],
    *,
    organization_id: str,
    project_ids: tuple[str, ...],
) -> bool:
    projects = {value.strip() for value in project_ids if value.strip()}
    for target in targets:
        if target.kind is AccessTargetKind.ALL:
            return True
        if target.kind is AccessTargetKind.ORGANIZATION and target.organization_id == organization_id:
            return True
        if target.kind is AccessTargetKind.PROJECT and target.project_id in projects:
            return True
        if (
            target.kind is AccessTargetKind.ORGANIZATION_PROJECT
            and target.organization_id == organization_id
            and target.project_id in projects
        ):
            return True
    return False


def _target_contains(ceiling: AccessTarget, requested: AccessTarget) -> bool:
    if ceiling.kind is AccessTargetKind.ALL:
        return True
    if ceiling.kind is AccessTargetKind.ORGANIZATION:
        return (
            requested.kind is AccessTargetKind.ORGANIZATION
            and requested.organization_id == ceiling.organization_id
        ) or (
            requested.kind is AccessTargetKind.ORGANIZATION_PROJECT
            and requested.organization_id == ceiling.organization_id
        )
    if ceiling.kind is AccessTargetKind.PROJECT:
        return requested.kind is AccessTargetKind.PROJECT and requested.project_id == ceiling.project_id
    if ceiling.kind is AccessTargetKind.ORGANIZATION_PROJECT:
        return (
            requested.kind is AccessTargetKind.ORGANIZATION_PROJECT
            and requested.organization_id == ceiling.organization_id
            and requested.project_id == ceiling.project_id
        )
    return False
