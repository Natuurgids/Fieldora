"""Persistent information barriers for governed Library evidence.

These records complement PBAC. PBAC answers whether an identity may perform an action;
an information-barrier contract answers whether this governed evidence is inside the
identity's permitted organization/project wall. The two checks are cumulative.

Collection walls are cumulative with asset walls. An asset-specific contract cannot
silently bypass a restricted collection that still contains the asset.

Contract mutation and tamper-evident audit sealing share one access-database transaction.
An unaudited governance change therefore cannot commit.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from natureai_next.server.access_audit_events import append_governance_audit
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
        value["targets"] = [
            {
                "kind": item.kind.value,
                "organization_id": item.organization_id,
                "project_id": item.project_id,
            }
            for item in self.targets
        ]
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
    """CREATE TABLE IF NOT EXISTS access_data_contract_targets(
        contract_id TEXT NOT NULL,
        target_kind TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        PRIMARY KEY(contract_id,target_kind,organization_id,project_id)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_access_data_contract_target_lookup
        ON access_data_contract_targets(target_kind,organization_id,project_id,contract_id)""",
    """CREATE TABLE IF NOT EXISTS access_data_contract_signatures(
        contract_id TEXT NOT NULL,
        owner_identity TEXT NOT NULL,
        signature_id TEXT NOT NULL,
        signed_at_epoch BIGINT NOT NULL,
        PRIMARY KEY(contract_id,signature_id)
    )""",
    """CREATE TABLE IF NOT EXISTS access_collection_assets(
        collection_id TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        PRIMARY KEY(collection_id,asset_id)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_access_collection_assets_asset
        ON access_collection_assets(asset_id,collection_id)""",
)


class AccessBarrierRepository:
    """Repository using the same connection factory as the authoritative access store."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory
        connection = factory.connect()
        try:
            # The access/audit repository is authoritative and must already exist.
            # Touching the chain here intentionally fails construction when callers try
            # to create a detached contract database without its audit foundation.
            connection.execute("SELECT sequence FROM access_audit_chain LIMIT 1").fetchone()
            for statement in _SCHEMA:
                connection.execute(statement)
            self._backfill_target_index(connection)
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
        targets_json = _targets_json(draft.targets)
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
            self._insert_targets(connection, identifier, draft.targets)
            if status == "active":
                self._supersede_other_active(
                    connection,
                    draft.subject,
                    identifier,
                    replaces_contract_id.strip(),
                )
            append_governance_audit(
                connection,
                subject_id=requested_by.strip(),
                action=(
                    "data_contract.requested"
                    if status == "pending"
                    else "data_contract.activated"
                ),
                resource_type="data_contract",
                resource_id=identifier,
                reason="governed evidence access contract persisted",
                request={
                    "subject_kind": draft.subject.kind.value,
                    "subject_id": draft.subject.subject_id,
                    "source_project_id": draft.source_project_id,
                    "targets": _target_dicts(draft.targets),
                    "status": status,
                    "replaces_contract_id": replaces_contract_id.strip(),
                    "required_owner_signatures": draft.required_owner_signatures,
                },
                occurred_at_utc=_epoch_utc(now),
            )
            if status == "active" and replaces_contract_id.strip():
                append_governance_audit(
                    connection,
                    subject_id=requested_by.strip(),
                    action="data_contract.superseded",
                    resource_type="data_contract",
                    resource_id=replaces_contract_id.strip(),
                    reason="replacement evidence access contract activated",
                    request={"replacement_contract_id": identifier},
                    occurred_at_utc=_epoch_utc(now),
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
            append_governance_audit(
                connection,
                subject_id=owner_identity.strip(),
                action="data_contract.attested",
                resource_type="data_contract",
                resource_id=contract_id,
                reason="recorded project owner attestation",
                request={
                    "signature_id": signature_id.strip(),
                    "attestation_number": count,
                    "required_attestations": required,
                    "source_project_id": str(row["source_project_id"]),
                },
                occurred_at_utc=_epoch_utc(now),
            )
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
                replaced = str(row["replaces_contract_id"])
                self._supersede_other_active(
                    connection,
                    subject,
                    contract_id,
                    replaced,
                )
                append_governance_audit(
                    connection,
                    subject_id=owner_identity.strip(),
                    action="data_contract.activated",
                    resource_type="data_contract",
                    resource_id=contract_id,
                    reason="required project-owner attestations completed",
                    request={
                        "subject_kind": subject.kind.value,
                        "subject_id": subject.subject_id,
                        "attestations": count,
                        "replaces_contract_id": replaced,
                    },
                    occurred_at_utc=_epoch_utc(now),
                )
                if replaced:
                    append_governance_audit(
                        connection,
                        subject_id=owner_identity.strip(),
                        action="data_contract.superseded",
                        resource_type="data_contract",
                        resource_id=replaced,
                        reason="approved sharing replacement activated",
                        request={"replacement_contract_id": contract_id},
                        occurred_at_utc=_epoch_utc(now),
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

    def link_collection_asset(
        self, collection_id: str, asset_id: str, *, actor_id: str = "system"
    ) -> None:
        if not collection_id.strip() or not asset_id.strip() or not actor_id.strip():
            raise ValueError("collection_id, asset_id and actor_id are required")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO access_collection_assets VALUES(?,?)",
                (collection_id.strip(), asset_id.strip()),
            )
            if cursor.rowcount:
                append_governance_audit(
                    connection,
                    subject_id=actor_id.strip(),
                    action="data_contract.collection_asset_linked",
                    resource_type="collection",
                    resource_id=collection_id.strip(),
                    reason="asset entered collection information-barrier scope",
                    request={"asset_id": asset_id.strip()},
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def unlink_collection_asset(
        self, collection_id: str, asset_id: str, *, actor_id: str = "system"
    ) -> None:
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM access_collection_assets WHERE collection_id=? AND asset_id=?",
                (collection_id.strip(), asset_id.strip()),
            )
            if cursor.rowcount:
                append_governance_audit(
                    connection,
                    subject_id=actor_id.strip(),
                    action="data_contract.collection_asset_unlinked",
                    resource_type="collection",
                    resource_id=collection_id.strip(),
                    reason="asset left collection information-barrier scope",
                    request={"asset_id": asset_id.strip()},
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def collections_for_asset(self, asset_id: str) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT collection_id FROM access_collection_assets "
                "WHERE asset_id=? ORDER BY collection_id",
                (asset_id.strip(),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(str(row[0]) for row in rows)

    def allows(
        self,
        subject: ContractSubject,
        *,
        organization_id: str,
        project_ids: tuple[str, ...] = (),
    ) -> bool:
        contract = self.current(subject)
        return contract is None or _contract_allows(
            contract,
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
        """Require every active asset/collection barrier covering the asset to allow."""
        subjects = [ContractSubject(ContractSubjectKind.ASSET, asset_id)]
        subjects.extend(
            ContractSubject(ContractSubjectKind.COLLECTION, collection_id)
            for collection_id in self.collections_for_asset(asset_id)
        )
        active = [contract for subject in subjects if (contract := self.current(subject))]
        if not active:
            return True
        return all(
            _contract_allows(
                contract,
                organization_id=organization_id,
                project_ids=project_ids,
            )
            for contract in active
        )

    def candidate_shared_assets(
        self,
        *,
        organization_id: str,
        project_ids: tuple[str, ...] = (),
        limit: int = 500,
    ) -> tuple[str, ...]:
        """Return indexed asset IDs whose active contracts target this recipient scope."""
        limit = max(1, min(int(limit), 5000))
        projects = tuple(sorted({value.strip() for value in project_ids if value.strip()}))
        clauses = [
            "t.target_kind='all'",
            "(t.target_kind='organization' AND t.organization_id=?)",
        ]
        parameters: list[object] = [organization_id]
        if projects:
            placeholders = ",".join("?" for _ in projects)
            clauses.append(f"(t.target_kind='project' AND t.project_id IN ({placeholders}))")
            parameters.extend(projects)
            clauses.append(
                "(t.target_kind='organization_project' AND t.organization_id=? "
                f"AND t.project_id IN ({placeholders}))"
            )
            parameters.append(organization_id)
            parameters.extend(projects)
        parameters.append(limit)
        sql = (
            "SELECT DISTINCT c.subject_kind,c.subject_id FROM access_data_contracts c "
            "JOIN access_data_contract_targets t ON t.contract_id=c.contract_id "
            "WHERE c.status='active' AND ("
            + " OR ".join(clauses)
            + ") ORDER BY c.subject_kind,c.subject_id LIMIT ?"
        )
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
            result: list[str] = []
            for row in rows:
                kind, subject_id = str(row[0]), str(row[1])
                if kind == ContractSubjectKind.ASSET.value:
                    if subject_id not in result:
                        result.append(subject_id)
                elif kind == ContractSubjectKind.COLLECTION.value:
                    members = connection.execute(
                        "SELECT asset_id FROM access_collection_assets "
                        "WHERE collection_id=? ORDER BY asset_id LIMIT ?",
                        (subject_id, limit),
                    ).fetchall()
                    for member in members:
                        asset_id = str(member[0])
                        if asset_id not in result:
                            result.append(asset_id)
                        if len(result) >= limit:
                            break
                if len(result) >= limit:
                    break
        finally:
            connection.close()
        return tuple(result[:limit])

    @staticmethod
    def _insert_targets(
        connection: Any, contract_id: str, targets: tuple[AccessTarget, ...]
    ) -> None:
        for target in targets:
            connection.execute(
                "INSERT OR IGNORE INTO access_data_contract_targets VALUES(?,?,?,?)",
                (
                    contract_id,
                    target.kind.value,
                    target.organization_id,
                    target.project_id,
                ),
            )

    @classmethod
    def _backfill_target_index(cls, connection: Any) -> None:
        rows = connection.execute(
            "SELECT contract_id,targets_json FROM access_data_contracts "
            "WHERE contract_id NOT IN (SELECT DISTINCT contract_id FROM access_data_contract_targets)"
        ).fetchall()
        for row in rows:
            cls._insert_targets(connection, str(row[0]), _parse_targets(str(row[1])))

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


def _contract_allows(
    contract: DataAccessContract,
    *,
    organization_id: str,
    project_ids: tuple[str, ...],
) -> bool:
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


def _targets_json(targets: tuple[AccessTarget, ...]) -> str:
    return json.dumps(_target_dicts(targets), sort_keys=True, separators=(",", ":"))


def _target_dicts(targets: tuple[AccessTarget, ...]) -> list[dict[str, str]]:
    return [
        {
            "kind": target.kind.value,
            "organization_id": target.organization_id,
            "project_id": target.project_id,
        }
        for target in targets
    ]


def _parse_targets(value: str) -> tuple[AccessTarget, ...]:
    raw_targets = json.loads(value)
    return tuple(
        AccessTarget(
            AccessTargetKind(str(item["kind"])),
            str(item.get("organization_id", "")),
            str(item.get("project_id", "")),
        )
        for item in raw_targets
    )


def _contract_row(row: Any) -> DataAccessContract:
    return DataAccessContract(
        contract_id=str(row["contract_id"]),
        subject_kind=str(row["subject_kind"]),
        subject_id=str(row["subject_id"]),
        source_project_id=str(row["source_project_id"]),
        status=str(row["status"]),
        targets=_parse_targets(str(row["targets_json"])),
        requires_owner_approval=bool(row["requires_owner_approval"]),
        required_owner_signatures=int(row["required_owner_signatures"]),
        requested_by=str(row["requested_by"]),
        replaces_contract_id=str(row["replaces_contract_id"]),
        created_at_epoch=int(row["created_at_epoch"]),
        activated_at_epoch=int(row["activated_at_epoch"]),
    )


def _epoch_utc(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat()
