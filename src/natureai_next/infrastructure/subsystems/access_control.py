"""Access-control subsystem database registration."""

from __future__ import annotations

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor


ACCESS_CONTROL_SUBSYSTEM_KEY = "security.access-control"

ACCESS_CONTROL_MIGRATIONS = (
    Migration(
        1,
        "identity PBAC contracts and audit",
        """
        CREATE TABLE IF NOT EXISTS access_schema_metadata(
            id INTEGER PRIMARY KEY CHECK(id=1),
            schema_family TEXT NOT NULL,
            default_policy TEXT NOT NULL
        );
        INSERT OR IGNORE INTO access_schema_metadata(id,schema_family,default_policy)
        VALUES(1,'fieldora-access-control','deny');
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
        """,
    ),
    Migration(
        2,
        "local credentials and opaque sessions",
        """
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
        """,
    ),
    Migration(
        3,
        "scoped service credentials",
        """
        CREATE TABLE IF NOT EXISTS access_service_credentials(
            credential_id TEXT PRIMARY KEY,identity_id TEXT NOT NULL,
            key_prefix TEXT NOT NULL UNIQUE,key_hash TEXT NOT NULL,
            label TEXT NOT NULL,created_at_utc TEXT NOT NULL,
            expires_at_utc TEXT NOT NULL,revoked_at_utc TEXT NOT NULL
        );
        """,
    ),
    Migration(
        4,
        "interactive device authorization",
        """
        CREATE TABLE IF NOT EXISTS access_device_authorizations(
            authorization_id TEXT PRIMARY KEY,device_code_hash TEXT NOT NULL UNIQUE,
            user_code_hash TEXT NOT NULL UNIQUE,device_name TEXT NOT NULL,
            organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,expires_at_utc TEXT NOT NULL,
            approved_by TEXT NOT NULL,approved_identity_id TEXT NOT NULL,
            approved_at_utc TEXT NOT NULL,consumed_at_utc TEXT NOT NULL
        );
        """,
    ),
    Migration(
        5,
        "federated OIDC identity mappings",
        """
        CREATE TABLE IF NOT EXISTS access_federated_identities(
            issuer TEXT NOT NULL,subject TEXT NOT NULL,identity_id TEXT NOT NULL,
            PRIMARY KEY(issuer,subject)
        );
        """,
    ),
    Migration(
        6,
        "tamper evident PBAC audit chain",
        """
        CREATE TABLE IF NOT EXISTS access_audit_chain(
            sequence INTEGER PRIMARY KEY,previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        );
        """,
    ),
)


def access_control_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        ACCESS_CONTROL_SUBSYSTEM_KEY, database_path, ACCESS_CONTROL_MIGRATIONS, True
    )
