"""SQLite repository for local identity, PBAC, contracts, and audit."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from natureai_next.domain.access_control import (
    Contract,
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteAccessControlRepository:
    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)
        self._ensure()

    def _ensure(self) -> None:
        connection = self._factory.connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS access_organizations(
                    organization_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS access_identities(
                    identity_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    display_name TEXT NOT NULL, organization_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    attributes_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_role_assignments(
                    subject_id TEXT NOT NULL, role_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    PRIMARY KEY(subject_id,role_id,organization_id,project_id)
                );
                CREATE TABLE IF NOT EXISTS access_group_members(
                    group_id TEXT NOT NULL, member_id TEXT NOT NULL,
                    PRIMARY KEY(group_id,member_id)
                );
                CREATE TABLE IF NOT EXISTS access_contracts(
                    contract_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    organization_id TEXT NOT NULL, starts_at_utc TEXT NOT NULL,
                    ends_at_utc TEXT NOT NULL, status TEXT NOT NULL,
                    terms_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_policies(
                    policy_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    effect TEXT NOT NULL, source TEXT NOT NULL, source_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL, role_id TEXT NOT NULL,
                    actions_json TEXT NOT NULL, resource_types_json TEXT NOT NULL,
                    resource_id TEXT NOT NULL, organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, purposes_json TEXT NOT NULL,
                    fields_json TEXT NOT NULL, conditions_json TEXT NOT NULL,
                    valid_from_utc TEXT NOT NULL, valid_until_utc TEXT NOT NULL,
                    priority INTEGER NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS access_audit_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at_utc TEXT NOT NULL, subject_id TEXT NOT NULL,
                    action TEXT NOT NULL, resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL, allowed INTEGER NOT NULL,
                    reason TEXT NOT NULL, policy_ids_json TEXT NOT NULL,
                    request_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_audit_chain(
                    sequence INTEGER PRIMARY KEY,previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_credentials(
                    identity_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    salt_hex TEXT NOT NULL, password_hash_hex TEXT NOT NULL,
                    iterations INTEGER NOT NULL, enabled INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_sessions(
                    session_hash TEXT PRIMARY KEY, identity_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, expires_at_utc TEXT NOT NULL,
                    revoked_at_utc TEXT NOT NULL, client_label TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_access_sessions_identity
                    ON access_sessions(identity_id,expires_at_utc);
                CREATE TABLE IF NOT EXISTS access_service_credentials(
                    credential_id TEXT PRIMARY KEY,identity_id TEXT NOT NULL,
                    key_prefix TEXT NOT NULL UNIQUE,key_hash TEXT NOT NULL,
                    label TEXT NOT NULL,created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,revoked_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_device_authorizations(
                    authorization_id TEXT PRIMARY KEY,device_code_hash TEXT NOT NULL UNIQUE,
                    user_code_hash TEXT NOT NULL UNIQUE,device_name TEXT NOT NULL,
                    organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,expires_at_utc TEXT NOT NULL,
                    approved_by TEXT NOT NULL,approved_identity_id TEXT NOT NULL,
                    approved_at_utc TEXT NOT NULL,consumed_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_federated_identities(
                    issuer TEXT NOT NULL,subject TEXT NOT NULL,identity_id TEXT NOT NULL,
                    PRIMARY KEY(issuer,subject)
                );
                """
            )
            if connection.execute(
                "SELECT COUNT(*) FROM access_audit_chain"
            ).fetchone()[0] == 0:
                self._seal_legacy_audit(connection)
        finally:
            connection.close()

    @staticmethod
    def _seal_legacy_audit(connection) -> None:
        previous_hash = "0" * 64
        rows = connection.execute(
            "SELECT * FROM access_audit_events ORDER BY sequence"
        ).fetchall()
        for row in rows:
            canonical = json.dumps(
                {
                    "sequence": int(row["sequence"]),
                    "occurred_at_utc": str(row["occurred_at_utc"]),
                    "subject_id": str(row["subject_id"]),
                    "action": str(row["action"]),
                    "resource_type": str(row["resource_type"]),
                    "resource_id": str(row["resource_id"]),
                    "allowed": bool(row["allowed"]),
                    "reason": str(row["reason"]),
                    "policy_ids": json.loads(str(row["policy_ids_json"])),
                    "request": json.loads(str(row["request_json"])),
                },
                sort_keys=True, separators=(",", ":"),
            )
            event_hash = hashlib.sha256((previous_hash + canonical).encode()).hexdigest()
            connection.execute(
                "INSERT INTO access_audit_chain VALUES(?,?,?)",
                (int(row["sequence"]), previous_hash, event_hash),
            )
            previous_hash = event_hash

    def put_credential(
        self, identity_id: str, username: str, salt_hex: str,
        password_hash_hex: str, iterations: int,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_credentials VALUES(?,?,?,?,?,1) "
                "ON CONFLICT(identity_id) DO UPDATE SET username=excluded.username,"
                "salt_hex=excluded.salt_hex,password_hash_hex=excluded.password_hash_hex,"
                "iterations=excluded.iterations,enabled=1",
                (identity_id, username, salt_hex, password_hash_hex, iterations),
            )
        finally:
            connection.close()

    def credential(self, username: str) -> dict | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM access_credentials WHERE username=?",
                (username,),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else dict(row)

    def put_session(
        self, token: str, identity_id: str, created_at_utc: str,
        expires_at_utc: str, client_label: str,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_sessions VALUES(?,?,?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(), identity_id,
                    created_at_utc, expires_at_utc, "", client_label,
                ),
            )
        finally:
            connection.close()

    def session(self, token: str, at_utc: str) -> dict | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM access_sessions WHERE session_hash=? "
                "AND revoked_at_utc='' AND expires_at_utc>?",
                (hashlib.sha256(token.encode()).hexdigest(), at_utc),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else dict(row)

    def revoke_session(self, token: str, revoked_at_utc: str) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE access_sessions SET revoked_at_utc=? WHERE session_hash=?",
                (revoked_at_utc, hashlib.sha256(token.encode()).hexdigest()),
            )
        finally:
            connection.close()

    def put_service_credential(self, record: dict) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_service_credentials VALUES(?,?,?,?,?,?,?,?)",
                (
                    record["credential_id"], record["identity_id"], record["key_prefix"],
                    record["key_hash"], record["label"], record["created_at_utc"],
                    record["expires_at_utc"], "",
                ),
            )
        finally:
            connection.close()

    def service_credential(self, key_prefix: str) -> dict | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM access_service_credentials WHERE key_prefix=?",
                (key_prefix,),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else dict(row)

    def revoke_service_credential(
        self, credential_id: str, revoked_at_utc: str
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE access_service_credentials SET revoked_at_utc=? "
                "WHERE credential_id=? AND revoked_at_utc=''",
                (revoked_at_utc, credential_id),
            )
        finally:
            connection.close()

    def put_device_authorization(self, record: dict) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_device_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record["authorization_id"], record["device_code_hash"],
                    record["user_code_hash"], record["device_name"],
                    record["organization_id"], record["project_id"],
                    record["created_at_utc"], record["expires_at_utc"], "", "", "", "",
                ),
            )
        finally:
            connection.close()

    def device_authorization(self, column: str, digest: str) -> dict | None:
        if column not in ("device_code_hash", "user_code_hash"):
            raise ValueError("invalid authorization lookup")
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                f"SELECT * FROM access_device_authorizations WHERE {column}=?",
                (digest,),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else dict(row)

    def approve_device_authorization(
        self, authorization_id: str, approver_id: str, device_identity_id: str,
        approved_at_utc: str,
    ) -> bool:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE access_device_authorizations SET approved_by=?,"
                "approved_identity_id=?,approved_at_utc=? WHERE authorization_id=? "
                "AND approved_at_utc='' AND consumed_at_utc=''",
                (approver_id, device_identity_id, approved_at_utc, authorization_id),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def consume_device_authorization(
        self, authorization_id: str, consumed_at_utc: str
    ) -> bool:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE access_device_authorizations SET consumed_at_utc=? "
                "WHERE authorization_id=? AND approved_at_utc<>'' AND consumed_at_utc=''",
                (consumed_at_utc, authorization_id),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def map_federated_identity(
        self, issuer: str, subject: str, identity_id: str
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_federated_identities VALUES(?,?,?) "
                "ON CONFLICT(issuer,subject) DO UPDATE SET identity_id=excluded.identity_id",
                (issuer, subject, identity_id),
            )
        finally:
            connection.close()

    def federated_identity(self, issuer: str, subject: str) -> Identity | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT identity_id FROM access_federated_identities "
                "WHERE issuer=? AND subject=?",
                (issuer, subject),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else self.identity(str(row[0]))

    def identity(self, identity_id: str) -> Identity | None:
        return next(
            (item for item in self.identities() if item.identity_id == identity_id), None
        )

    def put_organization(self, organization: Organization) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_organizations VALUES(?,?,?) "
                "ON CONFLICT(organization_id) DO UPDATE SET "
                "name=excluded.name,enabled=excluded.enabled",
                (
                    organization.organization_id, organization.name,
                    int(organization.enabled),
                ),
            )
        finally:
            connection.close()

    def organizations(self) -> tuple[Organization, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT * FROM access_organizations ORDER BY name,organization_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            Organization(
                str(row["organization_id"]), str(row["name"]), bool(row["enabled"])
            )
            for row in rows
        )

    def put_identity(self, identity: Identity) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_identities VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(identity_id) DO UPDATE SET kind=excluded.kind,"
                "display_name=excluded.display_name,organization_id=excluded.organization_id,"
                "enabled=excluded.enabled,attributes_json=excluded.attributes_json",
                (
                    identity.identity_id, identity.kind.value, identity.display_name,
                    identity.organization_id, int(identity.enabled),
                    json.dumps(identity.attributes, sort_keys=True),
                ),
            )
        finally:
            connection.close()

    def identities(self) -> tuple[Identity, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT * FROM access_identities ORDER BY display_name,identity_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            Identity(
                str(row["identity_id"]), IdentityKind(str(row["kind"])),
                str(row["display_name"]), str(row["organization_id"]),
                bool(row["enabled"]), json.loads(str(row["attributes_json"])),
            )
            for row in rows
        )

    def assign_role(
        self, subject_id: str, role_id: str, organization_id: str, project_id: str = ""
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO access_role_assignments VALUES(?,?,?,?)",
                (subject_id, role_id, organization_id, project_id),
            )
        finally:
            connection.close()

    def add_group_member(self, group_id: str, member_id: str) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO access_group_members VALUES(?,?)",
                (group_id, member_id),
            )
        finally:
            connection.close()

    def group_ids(self, member_id: str) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "WITH RECURSIVE memberships(group_id) AS ("
                "SELECT group_id FROM access_group_members WHERE member_id=? "
                "UNION SELECT gm.group_id FROM access_group_members gm "
                "JOIN memberships m ON gm.member_id=m.group_id"
                ") SELECT group_id FROM memberships",
                (member_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(str(row[0]) for row in rows)

    def role_ids(
        self, subject_id: str, organization_id: str, project_id: str
    ) -> tuple[str, ...]:
        principals = (subject_id, *self.group_ids(subject_id))
        placeholders = ",".join("?" for _ in principals)
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                f"SELECT DISTINCT role_id FROM access_role_assignments "
                f"WHERE subject_id IN ({placeholders}) "
                "AND organization_id IN ('',?) AND project_id IN ('',?)",
                (*principals, organization_id, project_id),
            ).fetchall()
        finally:
            connection.close()
        return tuple(str(row[0]) for row in rows)

    def put_contract(self, contract: Contract) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_contracts VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(contract_id) DO UPDATE SET title=excluded.title,"
                "organization_id=excluded.organization_id,starts_at_utc=excluded.starts_at_utc,"
                "ends_at_utc=excluded.ends_at_utc,status=excluded.status,"
                "terms_json=excluded.terms_json",
                (
                    contract.contract_id, contract.title, contract.organization_id,
                    contract.starts_at_utc, contract.ends_at_utc, contract.status,
                    json.dumps(contract.terms, sort_keys=True),
                ),
            )
        finally:
            connection.close()

    def replace_contract_if_current(
        self, contract: Contract, expected: Contract
    ) -> bool:
        """Replace a contract only if no concurrent approval changed it."""
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE access_contracts SET title=?,organization_id=?,"
                "starts_at_utc=?,ends_at_utc=?,status=?,terms_json=? "
                "WHERE contract_id=? AND status=? AND terms_json=?",
                (
                    contract.title, contract.organization_id,
                    contract.starts_at_utc, contract.ends_at_utc, contract.status,
                    json.dumps(contract.terms, sort_keys=True), contract.contract_id,
                    expected.status, json.dumps(expected.terms, sort_keys=True),
                ),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def contracts(self) -> tuple[Contract, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT * FROM access_contracts ORDER BY title,contract_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            Contract(
                str(row["contract_id"]), str(row["title"]),
                str(row["organization_id"]), str(row["starts_at_utc"]),
                str(row["ends_at_utc"]), str(row["status"]),
                json.loads(str(row["terms_json"])),
            )
            for row in rows
        )

    def contract(self, contract_id: str) -> Contract | None:
        return next(
            (item for item in self.contracts() if item.contract_id == contract_id), None
        )

    def put_policy(self, policy: Policy) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO access_policies VALUES("
                + ",".join("?" for _ in range(19))
                + ") ON CONFLICT(policy_id) DO UPDATE SET "
                + ",".join(
                    f"{name}=excluded.{name}"
                    for name in (
                        "name","effect","source","source_id","subject_id","role_id",
                        "actions_json","resource_types_json","resource_id",
                        "organization_id","project_id","purposes_json","fields_json",
                        "conditions_json","valid_from_utc","valid_until_utc","priority","enabled",
                    )
                ),
                (
                    policy.policy_id, policy.name, policy.effect.value, policy.source.value,
                    policy.source_id, policy.subject_id, policy.role_id,
                    json.dumps(policy.actions), json.dumps(policy.resource_types),
                    policy.resource_id, policy.organization_id, policy.project_id,
                    json.dumps(policy.purposes), json.dumps(policy.fields),
                    json.dumps(policy.conditions, sort_keys=True), policy.valid_from_utc,
                    policy.valid_until_utc, policy.priority, int(policy.enabled),
                ),
            )
        finally:
            connection.close()

    def put_contract_with_policies(
        self,
        contract: Contract,
        policies: tuple[Policy, ...],
        expected: Contract | None = None,
    ) -> bool:
        """Atomically activate a contract and all policies derived from it."""
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if expected is None:
                connection.execute(
                    "INSERT INTO access_contracts VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(contract_id) DO UPDATE SET title=excluded.title,"
                    "organization_id=excluded.organization_id,"
                    "starts_at_utc=excluded.starts_at_utc,"
                    "ends_at_utc=excluded.ends_at_utc,status=excluded.status,"
                    "terms_json=excluded.terms_json",
                    (
                        contract.contract_id, contract.title, contract.organization_id,
                        contract.starts_at_utc, contract.ends_at_utc, contract.status,
                        json.dumps(contract.terms, sort_keys=True),
                    ),
                )
            else:
                cursor = connection.execute(
                    "UPDATE access_contracts SET title=?,organization_id=?,"
                    "starts_at_utc=?,ends_at_utc=?,status=?,terms_json=? "
                    "WHERE contract_id=? AND status=? AND terms_json=?",
                    (
                        contract.title, contract.organization_id,
                        contract.starts_at_utc, contract.ends_at_utc, contract.status,
                        json.dumps(contract.terms, sort_keys=True), contract.contract_id,
                        expected.status, json.dumps(expected.terms, sort_keys=True),
                    ),
                )
                if cursor.rowcount != 1:
                    connection.execute("ROLLBACK")
                    return False
            for policy in policies:
                connection.execute(
                    "INSERT INTO access_policies VALUES("
                    + ",".join("?" for _ in range(19))
                    + ")",
                    (
                        policy.policy_id, policy.name, policy.effect.value,
                        policy.source.value, policy.source_id, policy.subject_id,
                        policy.role_id, json.dumps(policy.actions),
                        json.dumps(policy.resource_types), policy.resource_id,
                        policy.organization_id, policy.project_id,
                        json.dumps(policy.purposes), json.dumps(policy.fields),
                        json.dumps(policy.conditions, sort_keys=True),
                        policy.valid_from_utc, policy.valid_until_utc,
                        policy.priority, int(policy.enabled),
                    ),
                )
            connection.execute("COMMIT")
            return True
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def policies(self) -> tuple[Policy, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT * FROM access_policies ORDER BY priority DESC,name,policy_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            Policy(
                policy_id=str(row["policy_id"]), name=str(row["name"]),
                effect=PolicyEffect(str(row["effect"])),
                source=PolicySource(str(row["source"])),
                source_id=str(row["source_id"]), subject_id=str(row["subject_id"]),
                role_id=str(row["role_id"]),
                actions=tuple(json.loads(str(row["actions_json"]))),
                resource_types=tuple(json.loads(str(row["resource_types_json"]))),
                resource_id=str(row["resource_id"]),
                organization_id=str(row["organization_id"]),
                project_id=str(row["project_id"]),
                purposes=tuple(json.loads(str(row["purposes_json"]))),
                fields=tuple(json.loads(str(row["fields_json"]))),
                conditions=json.loads(str(row["conditions_json"])),
                valid_from_utc=str(row["valid_from_utc"]),
                valid_until_utc=str(row["valid_until_utc"]),
                priority=int(row["priority"]), enabled=bool(row["enabled"]),
            )
            for row in rows
        )

    def append_audit(self, event: dict) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "INSERT INTO access_audit_events("
                "occurred_at_utc,subject_id,action,resource_type,resource_id,allowed,"
                "reason,policy_ids_json,request_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event["occurred_at_utc"], event["subject_id"], event["action"],
                    event["resource_type"], event["resource_id"], int(event["allowed"]),
                    event["reason"], json.dumps(event["policy_ids"]),
                    json.dumps(event["request"], sort_keys=True),
                ),
            )
            sequence = int(cursor.lastrowid)
            previous_row = connection.execute(
                "SELECT event_hash FROM access_audit_chain ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = "0" * 64 if previous_row is None else str(previous_row[0])
            canonical = json.dumps(
                {
                    "sequence": sequence,
                    "occurred_at_utc": event["occurred_at_utc"],
                    "subject_id": event["subject_id"],
                    "action": event["action"],
                    "resource_type": event["resource_type"],
                    "resource_id": event["resource_id"],
                    "allowed": bool(event["allowed"]),
                    "reason": event["reason"],
                    "policy_ids": event["policy_ids"],
                    "request": event["request"],
                },
                sort_keys=True, separators=(",", ":"),
            )
            event_hash = hashlib.sha256(
                (previous_hash + canonical).encode()
            ).hexdigest()
            connection.execute(
                "INSERT INTO access_audit_chain VALUES(?,?,?)",
                (sequence, previous_hash, event_hash),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def audit_events(self, limit: int = 200) -> tuple[dict, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT * FROM access_audit_events ORDER BY sequence DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(dict(row) for row in rows)

    def verify_audit_chain(self) -> tuple[bool, str]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT e.*,c.previous_hash,c.event_hash FROM access_audit_events e "
                "LEFT JOIN access_audit_chain c ON c.sequence=e.sequence "
                "ORDER BY e.sequence"
            ).fetchall()
            chain_count = int(
                connection.execute("SELECT COUNT(*) FROM access_audit_chain").fetchone()[0]
            )
        finally:
            connection.close()
        if chain_count != len(rows):
            return False, "audit event/chain count mismatch"
        previous_hash = "0" * 64
        for row in rows:
            if row["event_hash"] is None or str(row["previous_hash"]) != previous_hash:
                return False, f"broken predecessor at sequence {row['sequence']}"
            canonical = json.dumps(
                {
                    "sequence": int(row["sequence"]),
                    "occurred_at_utc": str(row["occurred_at_utc"]),
                    "subject_id": str(row["subject_id"]),
                    "action": str(row["action"]),
                    "resource_type": str(row["resource_type"]),
                    "resource_id": str(row["resource_id"]),
                    "allowed": bool(row["allowed"]),
                    "reason": str(row["reason"]),
                    "policy_ids": json.loads(str(row["policy_ids_json"])),
                    "request": json.loads(str(row["request_json"])),
                },
                sort_keys=True, separators=(",", ":"),
            )
            expected = hashlib.sha256((previous_hash + canonical).encode()).hexdigest()
            if not hmac.compare_digest(expected, str(row["event_hash"])):
                return False, f"event hash mismatch at sequence {row['sequence']}"
            previous_hash = expected
        return True, f"{len(rows)} audit events verified"
