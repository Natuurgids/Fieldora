"""Persistent information barriers for governed Library evidence.

These records complement PBAC. PBAC answers whether an identity may perform an action;
an information-barrier contract answers whether this governed evidence is inside the
identity's permitted organization/project wall. The two checks are cumulative.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from uuid import uuid4

from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
)


@dataclass(frozen=True, slots=True)
class DataAccessContract:
    contract_id: str
    subject_kind: str
    subject_id: str
    source_project_id: str
    status: str
    targets: tuple[AccessTarget, ...]
    requires_owner_approval: bool
    required_owner_signatures: int
    requested_by: str
    replaces_contract_id: str
    created_at_epoch: int
    activated_at_epoch: int

    @property
    def subject(self) -> ContractSubject:
        return ContractSubject(ContractSubjectKind(self.subject_kind), self.subject_id)

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["targets"] = [asdict(item) for item in self.targets]
        return value


@dataclass(frozen=True, slots=True)
class ContractSignature:
    contract_id: str
    owner_identity: str
    signature_id: str
    signed_at_epoch: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class ConnectionFactory(Protocol):
    def connect(self, *, read_only: bool = False) -> Any: ...


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS access_data_contracts(
        contract_id TEXT PRIMARY KEY,
        subject_kind TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        source_project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        targets_json TEXT NOT NULL,
        requires_owner_approval INTEGER NOT NULL,
        required_owner_signatures INTEGER NOT NULL,
        requested_by TEXT NOT NULL,
        replaces_contract_id TEXT NOT NULL,
        created_at_epoch BIGINT NOT NULL,
        activated_at_epoch BIGINT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS ix_access_data_contract_subject
        ON access_data_contracts(subject_kind,subject_id,status,created_at_epoch)""",
    """CREATE TABLE IF NOT EXISTS access_data_contract_signatures(
        contract_id TEXT NOT NULL,
        owner_identity TEXT NOT NULL,
        signature_id TEXT NOT NULL,
        signed_at_epoch BIGINT NOT NULL,
        PRIMARY KEY(contract_id,signature_id)
    )""",
)


class AccessBarrierRepository:
    """Repository using the same connection factory as the authoritative access store."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory
        connection = factory.connect()
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
        finally:
            connection.close()

    def create(
        self,
        draft: ContractDraft,
        *,
        requested_by: str,
        replaces_contract_id: str = "",
        contract_id: str = "",
        now_epoch: int | None = None,
    ) -> DataAccessContract:
        if draft.subject is None:
            raise ValueError("persistent contract requires an asset or collection subject")
        if not requested_by.strip():
            raise ValueError("requested_by is required")
        if not draft.targets and not draft.inherited_contract_id:
            raise ValueError("contract requires targets or an inherited contract")
        if draft.inherited_contract_id and not draft.targets:
            raise ValueError("inherited intake must resolve its governing targets before persistence")
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        identifier = contract_id.strip() or str(uuid4())
        status = "pending" if draft.requires_project_owner_approval else "active"
        activated = 0 if status == "pending" else now
        targets_json = json.dumps(
            [
                {
                    "kind": target.kind.value,
                    "organization_id": target.organization_id,
                    "project_id": target.project_id,
                }
                for target in draft.targets
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if replaces_contract_id:
                previous = connection.execute(
                    "SELECT subject_kind,subject_id,status FROM access_data_contracts "
                    "WHERE contract_id=?",
                    (replaces_contract_id,),
                ).fetchone()
                if previous is None:
                    raise KeyError(replaces_contract_id)
                if (
                    str(previous["subject_kind"]) != draft.subject.kind.value
                    or str(previous["subject_id"]) != draft.subject.subject_id
                ):
                    raise ValueError("replacement contract subject does not match")
                if str(previous["status"]) != "active":
                    raise ValueError("only the active contract may be replaced")
            connection.execute(
                "INSERT INTO access_data_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    draft.subject.kind.value,
                    draft.subject.subject_id,
                    draft.source_project_id,
                    status,
                    targets_json,
                    int(draft.requires_project_owner_approval),
                    draft.required_owner_signatures,
                    requested_by.strip(),
                    replaces_contract_id.strip(),
                    now,
                    activated,
                ),
            )
            if status == "active":
                self._supersede_other_active(
                    connection,
                    draft.subject,
                    identifier,
                    replaces_contract_id.strip(),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        result = self.contract(identifier)
        assert result is not None
        return result

    def contract(self, contract_id: str) -> DataAccessContract | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM access_data_contracts WHERE contract_id=?",
                (contract_id,),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _contract_row(row)

    def current(self, subject: ContractSubject) -> DataAccessContract | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM access_data_contracts "
                "WHERE subject_kind=? AND subject_id=? AND status='active' "
                "ORDER BY activated_at_epoch DESC,created_at_epoch DESC,contract_id DESC LIMIT 1",
                (subject.kind.value, subject.subject_id),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _contract_row(row)

    def sign(
        self,
        contract_id: str,
        *,
        owner_identity: str,
        signature_id: str,
        now_epoch: int | None = None,
    ) -> DataAccessContract:
        if not owner_identity.strip() or not signature_id.strip():
            raise ValueError("owner identity and signature id are required")
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM access_data_contracts WHERE contract_id=?",
                (contract_id,),
            ).fetchone()
            if row is None:
                raise KeyError(contract_id)
            if str(row["status"]) != "pending":
                raise ValueError("contract is not awaiting approval")
            if not bool(row["requires_owner_approval"]):
                raise ValueError("contract does not require owner approval")
            existing_owner = connection.execute(
                "SELECT owner_identity FROM access_data_contract_signatures "
                "WHERE contract_id=? LIMIT 1",
                (contract_id,),
            ).fetchone()
            if existing_owner is not None and str(existing_owner[0]) != owner_identity.strip():
                raise PermissionError("both attestations must be made by the same project owner")
            connection.execute(
                "INSERT INTO access_data_contract_signatures VALUES(?,?,?,?)",
                (contract_id, owner_identity.strip(), signature_id.strip(), now),
            )
            count_row = connection.execute(
                "SELECT COUNT(*) FROM access_data_contract_signatures WHERE contract_id=?",
                (contract_id,),
            ).fetchone()
            count = int(count_row[0])
            required = int(row["required_owner_signatures"])
            if count >= required:
                connection.execute(
                    "UPDATE access_data_contracts SET status='active',activated_at_epoch=? "
                    "WHERE contract_id=? AND status='pending'",
                    (now, contract_id),
                )
                subject = ContractSubject(
                    ContractSubjectKind(str(row["subject_kind"])),
                    str(row["subject_id"]),
                )
                self._supersede_other_active(
                    connection,
                    subject,
                    contract_id,
                    str(row["replaces_contract_id"]),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        result = self.contract(contract_id)
        assert result is not None
        return result

    def signatures(self, contract_id: str) -> tuple[ContractSignature, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT contract_id,owner_identity,signature_id,signed_at_epoch "
                "FROM access_data_contract_signatures WHERE contract_id=? "
                "ORDER BY signed_at_epoch,signature_id",
                (contract_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(ContractSignature(*row) for row in rows)

    def allows(
        self,
        subject: ContractSubject,
        *,
        organization_id: str,
        project_ids: tuple[str, ...] = (),
    ) -> bool:
        contract = self.current(subject)
        if contract is None:
            # Legacy/uncontracted evidence remains governed by PBAC alone. New intake
            # is expected to receive an explicit contract before publication.
            return True
        projects = {value.strip() for value in project_ids if value.strip()}
        for target in contract.targets:
            if target.kind is AccessTargetKind.ALL:
                return True
            if (
                target.kind is AccessTargetKind.ORGANIZATION
                and target.organization_id == organization_id
            ):
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

    @staticmethod
    def _supersede_other_active(
        connection: Any,
        subject: ContractSubject,
        new_contract_id: str,
        replaces_contract_id: str,
    ) -> None:
        if replaces_contract_id:
            connection.execute(
                "UPDATE access_data_contracts SET status='superseded' "
                "WHERE contract_id=? AND status='active'",
                (replaces_contract_id,),
            )
        connection.execute(
            "UPDATE access_data_contracts SET status='superseded' "
            "WHERE subject_kind=? AND subject_id=? AND status='active' AND contract_id<>?",
            (subject.kind.value, subject.subject_id, new_contract_id),
        )


def _contract_row(row: Any) -> DataAccessContract:
    raw_targets = json.loads(str(row["targets_json"]))
    targets = tuple(
        AccessTarget(
            AccessTargetKind(str(item["kind"])),
            str(item.get("organization_id", "")),
            str(item.get("project_id", "")),
        )
        for item in raw_targets
    )
    return DataAccessContract(
        contract_id=str(row["contract_id"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        source_project_id=str(row["source_project_id"]),
        status=str(row["status"]),
        targets=targets,
        requires_owner_approval=bool(row["requires_owner_approval"]),
        required_owner_signatures=int(row["required_owner_signatures"]),
        requested_by=str(row["requested_by"]),
        replaces_contract_id=str(row["replaces_contract_id"]),
        created_at_epoch=int(row["created_at_epoch"]),
        activated_at_epoch=int(row["activated_at_epoch"]),
    )
