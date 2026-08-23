"""Fail-closed contract requirements for newly governed evidence.

Legacy evidence may remain PBAC-only during migration. New intake is explicitly marked
as requiring an active data-access contract; if contract derivation or activation fails,
the evidence stays preserved but is not disclosed. Project-governed sharing additionally
requires both attestations to come from the persisted owner of the source project.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from natureai_next.server.access_barriers import AccessBarrierRepository
from natureai_next.server.access_contracts import ContractSubject, ContractSubjectKind


@dataclass(frozen=True, slots=True)
class ProjectContractOwner:
    project_id: str
    owner_identity: str
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
        if any(
            self.contract_required(subject) and self.current(subject) is None
            for subject in subjects
        ):
            return False
        return super().allows_asset(
            asset_id,
            organization_id=organization_id,
            project_ids=project_ids,
        )
