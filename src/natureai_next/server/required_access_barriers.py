"""Fail-closed contract requirements for newly governed evidence.

Legacy evidence may remain PBAC-only during migration. New intake is explicitly marked
as requiring an active data-access contract; if contract derivation or activation fails,
the evidence stays preserved but is not disclosed.
"""

from __future__ import annotations

import time

from natureai_next.server.access_barriers import AccessBarrierRepository
from natureai_next.server.access_contracts import ContractSubject, ContractSubjectKind


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
