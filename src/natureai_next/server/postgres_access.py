"""PostgreSQL parity adapter for identity, PBAC, contracts, and audit."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


class _HybridRow(Mapping[str, Any]):
    def __init__(self, names: tuple[str, ...], values: tuple[Any, ...]) -> None:
        self._names = names
        self._values = values
        self._mapping = dict(zip(names, values, strict=True))

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __len__(self) -> int:
        return len(self._names)


class _Cursor:
    def __init__(self, cursor: Any, lastrowid: int | None = None) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def fetchone(self) -> _HybridRow | None:
        row = self._cursor.fetchone()
        return None if row is None else self._row(row)

    def fetchall(self) -> list[_HybridRow]:
        return [self._row(row) for row in self._cursor.fetchall()]

    def _row(self, row: Any) -> _HybridRow:
        names = tuple(str(item.name) for item in self._cursor.description)
        return _HybridRow(names, tuple(row))


class _Connection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.in_transaction = False

    def execute(self, sql: str, parameters: tuple = ()) -> _Cursor:
        normalized = sql.strip()
        upper = normalized.upper()
        if upper == "BEGIN IMMEDIATE":
            normalized = "BEGIN"
            self.in_transaction = True
        elif upper == "BEGIN":
            self.in_transaction = True
        elif upper == "COMMIT":
            self._connection.commit()
            self.in_transaction = False
            return _Cursor(self._connection.cursor())
        elif upper == "ROLLBACK":
            self._connection.rollback()
            self.in_transaction = False
            return _Cursor(self._connection.cursor())
        normalized = normalized.replace("?", "%s")
        if re.match(r"^INSERT OR IGNORE INTO ", normalized, re.IGNORECASE):
            normalized = re.sub(
                r"^INSERT OR IGNORE INTO ", "INSERT INTO ", normalized,
                flags=re.IGNORECASE,
            )
            normalized += " ON CONFLICT DO NOTHING"
        cursor = self._connection.cursor()
        lastrowid = None
        if re.match(
            r"^INSERT INTO access_audit_events\(", normalized, re.IGNORECASE
        ):
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("fieldora-access-audit",),
            )
            normalized += " RETURNING sequence"
            cursor.execute(normalized, parameters)
            returned = cursor.fetchone()
            lastrowid = int(returned[0])
        else:
            cursor.execute(normalized, parameters)
        return _Cursor(cursor, lastrowid)

    def commit(self) -> None:
        self._connection.commit()
        self.in_transaction = False

    def rollback(self) -> None:
        self._connection.rollback()
        self.in_transaction = False

    def close(self) -> None:
        self._connection.close()


class _Factory:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def connect(self, *, read_only: bool = False) -> _Connection:
        connection = self._connect()
        connection.autocommit = True
        return _Connection(connection)


class PostgresAccessControlRepository(SqliteAccessControlRepository):
    """Runs the complete access-control contract on a PostgreSQL schema."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._factory = _Factory(connect)
        self._ensure_postgres()

    def _ensure_postgres(self) -> None:
        connection = self._factory.connect()
        try:
            statements = (
                """CREATE TABLE IF NOT EXISTS access_organizations(
                    organization_id TEXT PRIMARY KEY,name TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))""",
                """CREATE TABLE IF NOT EXISTS access_identities(
                    identity_id TEXT PRIMARY KEY,kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,organization_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    attributes_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_role_assignments(
                    subject_id TEXT NOT NULL,role_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    PRIMARY KEY(subject_id,role_id,organization_id,project_id))""",
                """CREATE TABLE IF NOT EXISTS access_group_members(
                    group_id TEXT NOT NULL,member_id TEXT NOT NULL,
                    PRIMARY KEY(group_id,member_id))""",
                """CREATE TABLE IF NOT EXISTS access_contracts(
                    contract_id TEXT PRIMARY KEY,title TEXT NOT NULL,
                    organization_id TEXT NOT NULL,starts_at_utc TEXT NOT NULL,
                    ends_at_utc TEXT NOT NULL,status TEXT NOT NULL,
                    terms_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_policies(
                    policy_id TEXT PRIMARY KEY,name TEXT NOT NULL,effect TEXT NOT NULL,
                    source TEXT NOT NULL,source_id TEXT NOT NULL,subject_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,actions_json TEXT NOT NULL,
                    resource_types_json TEXT NOT NULL,resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    purposes_json TEXT NOT NULL,fields_json TEXT NOT NULL,
                    conditions_json TEXT NOT NULL,valid_from_utc TEXT NOT NULL,
                    valid_until_utc TEXT NOT NULL,priority INTEGER NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))""",
                """CREATE TABLE IF NOT EXISTS access_audit_events(
                    sequence BIGSERIAL PRIMARY KEY,occurred_at_utc TEXT NOT NULL,
                    subject_id TEXT NOT NULL,action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,
                    allowed INTEGER NOT NULL,reason TEXT NOT NULL,
                    policy_ids_json TEXT NOT NULL,request_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_audit_chain(
                    sequence BIGINT PRIMARY KEY,previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_credentials(
                    identity_id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,
                    salt_hex TEXT NOT NULL,password_hash_hex TEXT NOT NULL,
                    iterations INTEGER NOT NULL,enabled INTEGER NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_sessions(
                    session_hash TEXT PRIMARY KEY,identity_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,expires_at_utc TEXT NOT NULL,
                    revoked_at_utc TEXT NOT NULL,client_label TEXT NOT NULL)""",
                """CREATE INDEX IF NOT EXISTS ix_access_sessions_identity_pg
                    ON access_sessions(identity_id,expires_at_utc)""",
                """CREATE TABLE IF NOT EXISTS access_service_credentials(
                    credential_id TEXT PRIMARY KEY,identity_id TEXT NOT NULL,
                    key_prefix TEXT NOT NULL UNIQUE,key_hash TEXT NOT NULL,
                    label TEXT NOT NULL,created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,revoked_at_utc TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_device_authorizations(
                    authorization_id TEXT PRIMARY KEY,
                    device_code_hash TEXT NOT NULL UNIQUE,
                    user_code_hash TEXT NOT NULL UNIQUE,device_name TEXT NOT NULL,
                    organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,expires_at_utc TEXT NOT NULL,
                    approved_by TEXT NOT NULL,approved_identity_id TEXT NOT NULL,
                    approved_at_utc TEXT NOT NULL,consumed_at_utc TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS access_federated_identities(
                    issuer TEXT NOT NULL,subject TEXT NOT NULL,identity_id TEXT NOT NULL,
                    PRIMARY KEY(issuer,subject))""",
            )
            for statement in statements:
                connection.execute(statement)
        finally:
            connection.close()
