"""Audited organizational deletion approval and deterministic approver routing."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


ADMIN_ROLES = {"administrator", "admin", "tool-administrator", "tool_admin"}


@dataclass(frozen=True, slots=True)
class ApprovalPrincipal:
    identity_id: str
    display_name: str
    organization_id: str
    roles: tuple[str, ...]
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    request_id: str
    resource_id: str
    organization_id: str
    requested_by: str
    assigned_to: str
    target_kind: str
    target_value: str
    state: str
    reason: str
    routing_reason: str
    created_at_us: int


class ApproverResolver:
    """Resolve person/function targets, then fall back to a tool administrator."""

    @staticmethod
    def resolve(
        *,
        requester_id: str,
        organization_id: str,
        target_kind: str,
        target_value: str,
        principals: tuple[ApprovalPrincipal, ...],
    ) -> tuple[str, str]:
        eligible = tuple(
            item
            for item in principals
            if item.enabled and item.organization_id == organization_id
        )
        independent = tuple(item for item in eligible if item.identity_id != requester_id)
        if target_kind == "person":
            person = next(
                (item for item in independent if item.identity_id == target_value), None
            )
            if person is not None:
                return person.identity_id, "named-person"
        if target_kind == "function":
            role = target_value.strip().casefold()
            owner = next(
                (
                    item
                    for item in independent
                    if role in {value.casefold() for value in item.roles}
                ),
                None,
            )
            if owner is not None:
                return owner.identity_id, f"organization-function:{target_value}"
        administrator = next(
            (
                item
                for item in independent
                if ADMIN_ROLES.intersection(value.casefold() for value in item.roles)
            ),
            None,
        )
        if administrator is not None:
            return administrator.identity_id, "administrator-fallback"
        requester = next((item for item in eligible if item.identity_id == requester_id), None)
        if requester is not None and ADMIN_ROLES.intersection(
            value.casefold() for value in requester.roles
        ):
            return requester.identity_id, "sole-administrator-fallback"
        return "fieldora-tool-administrator", "tool-administrator-fallback"


class DeletionApprovalService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS deletion_requests(
                    request_id TEXT PRIMARY KEY,resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,requested_by TEXT NOT NULL,
                    assigned_to TEXT NOT NULL,target_kind TEXT NOT NULL,
                    target_value TEXT NOT NULL,state TEXT NOT NULL,
                    reason TEXT NOT NULL,routing_reason TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,resolved_at_us INTEGER,
                    resolved_by TEXT NOT NULL DEFAULT '',resolution_note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS ix_deletion_approval_queue
                    ON deletion_requests(assigned_to,state,created_at_us);
                CREATE TABLE IF NOT EXISTS deletion_approval_audit(
                    event_id TEXT PRIMARY KEY,request_id TEXT NOT NULL,
                    action TEXT NOT NULL,actor_id TEXT NOT NULL,
                    detail TEXT NOT NULL,created_at_us INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def request(
        self,
        *,
        resource_id: str,
        organization_id: str,
        requested_by: str,
        target_kind: str,
        target_value: str,
        reason: str,
        principals: tuple[ApprovalPrincipal, ...],
    ) -> DeletionRequest:
        assigned_to, routing_reason = ApproverResolver.resolve(
            requester_id=requested_by,
            organization_id=organization_id,
            target_kind=target_kind,
            target_value=target_value,
            principals=principals,
        )
        request_id = str(uuid4())
        now = time.time_ns() // 1000
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO deletion_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,'','')",
                (
                    request_id, resource_id, organization_id, requested_by,
                    assigned_to, target_kind, target_value, "pending",
                    reason.strip(), routing_reason, now,
                ),
            )
            self._audit(connection, request_id, "requested", requested_by, routing_reason)
        return self.get(request_id)

    def get(self, request_id: str) -> DeletionRequest:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM deletion_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return self._row(row)

    def list(self, state: str = "pending") -> tuple[DeletionRequest, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM deletion_requests WHERE state=? ORDER BY created_at_us",
                (state,),
            ).fetchall()
        return tuple(self._row(row) for row in rows)

    def resolve(
        self, request_id: str, *, approver_id: str, approve: bool, note: str = ""
    ) -> DeletionRequest:
        now = time.time_ns() // 1000
        state = "approved" if approve else "rejected"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT assigned_to,state FROM deletion_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            if str(row["state"]) != "pending":
                raise ValueError("deletion request is already resolved")
            if str(row["assigned_to"]) not in {
                approver_id,
                "fieldora-tool-administrator",
            }:
                raise PermissionError("request is assigned to another approver")
            connection.execute(
                "UPDATE deletion_requests SET state=?,resolved_at_us=?,resolved_by=?,"
                "resolution_note=? WHERE request_id=?",
                (state, now, approver_id, note.strip(), request_id),
            )
            self._audit(connection, request_id, state, approver_id, note)
        return self.get(request_id)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        request_id: str,
        action: str,
        actor_id: str,
        detail: str,
    ) -> None:
        connection.execute(
            "INSERT INTO deletion_approval_audit VALUES(?,?,?,?,?,?)",
            (str(uuid4()), request_id, action, actor_id, detail, time.time_ns() // 1000),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> DeletionRequest:
        return DeletionRequest(
            request_id=str(row["request_id"]),
            resource_id=str(row["resource_id"]),
            organization_id=str(row["organization_id"]),
            requested_by=str(row["requested_by"]),
            assigned_to=str(row["assigned_to"]),
            target_kind=str(row["target_kind"]),
            target_value=str(row["target_value"]),
            state=str(row["state"]),
            reason=str(row["reason"]),
            routing_reason=str(row["routing_reason"]),
            created_at_us=int(row["created_at_us"]),
        )
