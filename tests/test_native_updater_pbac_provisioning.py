from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import AccessRequest
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.infrastructure.subsystems.access_control import ACCESS_CONTROL_MIGRATIONS


def _provision(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS, "security-test").apply(connection)
    finally:
        connection.close()


def _install_request(subject_id: str) -> AccessRequest:
    return AccessRequest(
        subject_id=subject_id,
        action="install",
        resource_type="security_install_release",
        purpose="security_install",
    )


def test_clean_install_provisions_exact_native_updater_identity_and_permission(tmp_path: Path) -> None:
    database = tmp_path / "access-control.sqlite3"
    _provision(database)

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        identity = connection.execute(
            "SELECT * FROM access_identities WHERE identity_id='fieldora-native-updater'"
        ).fetchone()
        policies = connection.execute(
            "SELECT * FROM access_policies WHERE subject_id='fieldora-native-updater' AND enabled=1"
        ).fetchall()
    finally:
        connection.close()

    assert identity is not None
    assert identity["kind"] == "service"
    assert identity["enabled"] == 1
    assert len(policies) == 1
    policy = policies[0]
    assert policy["effect"] == "allow"
    assert json.loads(policy["actions_json"]) == ["install"]
    assert json.loads(policy["resource_types_json"]) == ["security_install_release"]
    assert json.loads(policy["purposes_json"]) == ["security_install"]
    assert policy["resource_id"] == ""
    assert policy["organization_id"] == ""
    assert policy["project_id"] == ""


def test_native_updater_provisioning_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "access-control.sqlite3"
    _provision(database)
    _provision(database)

    connection = sqlite3.connect(database)
    try:
        identity_count = connection.execute(
            "SELECT COUNT(*) FROM access_identities WHERE identity_id='fieldora-native-updater'"
        ).fetchone()[0]
        policy_count = connection.execute(
            "SELECT COUNT(*) FROM access_policies WHERE policy_id='fieldora-native-updater-security-install'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert identity_count == 1
    assert policy_count == 1


def test_unrelated_subject_remains_denied(tmp_path: Path) -> None:
    database = tmp_path / "access-control.sqlite3"
    _provision(database)
    decision = PolicyDecisionService(SqliteAccessControlRepository(database)).decide(
        _install_request("unrelated-service")
    )
    assert not decision.allowed


def test_missing_or_disabled_updater_identity_is_denied(tmp_path: Path) -> None:
    for mode in ("missing", "disabled"):
        database = tmp_path / f"{mode}.sqlite3"
        _provision(database)
        connection = sqlite3.connect(database)
        try:
            if mode == "missing":
                connection.execute(
                    "DELETE FROM access_identities WHERE identity_id='fieldora-native-updater'"
                )
            else:
                connection.execute(
                    "UPDATE access_identities SET enabled=0 WHERE identity_id='fieldora-native-updater'"
                )
            connection.commit()
        finally:
            connection.close()
        decision = PolicyDecisionService(SqliteAccessControlRepository(database)).decide(
            _install_request("fieldora-native-updater")
        )
        assert not decision.allowed


@pytest.mark.parametrize(
    ("action", "resource_type", "purpose"),
    [
        ("administer", "security_install_release", "security_install"),
        ("install", "access_policy", "security_install"),
        ("install", "security_install_release", "administration"),
    ],
)
def test_native_updater_is_denied_outside_exact_permission(
    tmp_path: Path, action: str, resource_type: str, purpose: str
) -> None:
    database = tmp_path / "access-control.sqlite3"
    _provision(database)
    decision = PolicyDecisionService(SqliteAccessControlRepository(database)).decide(
        AccessRequest(
            subject_id="fieldora-native-updater",
            action=action,
            resource_type=resource_type,
            purpose=purpose,
        )
    )
    assert not decision.allowed


def test_provisioning_removes_inherited_or_legacy_updater_authority(tmp_path: Path) -> None:
    database = tmp_path / "access-control.sqlite3"
    connection = sqlite3.connect(database)
    try:
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS[:6], "security-test").apply(connection)
        connection.execute(
            "INSERT INTO access_identities(identity_id,kind,display_name,organization_id,enabled,attributes_json) "
            "VALUES('fieldora-native-updater','user','Legacy updater','legacy-org',1,'{\"platform_admin\":\"true\"}')"
        )
        connection.execute(
            "INSERT INTO access_role_assignments(subject_id,role_id,organization_id,project_id) "
            "VALUES('fieldora-native-updater','platform-admin','','')"
        )
        connection.execute(
            "INSERT INTO access_group_members(group_id,member_id) VALUES('legacy-admins','fieldora-native-updater')"
        )
        connection.execute(
            "INSERT INTO access_policies(policy_id,name,effect,source,source_id,subject_id,role_id," 
            "actions_json,resource_types_json,resource_id,organization_id,project_id,purposes_json," 
            "fields_json,conditions_json,valid_from_utc,valid_until_utc,priority,enabled) VALUES(" 
            "'legacy-updater-admin','Legacy updater admin','allow','direct','legacy','fieldora-native-updater',''," 
            "'[\"*\"]','[\"*\"]','','','','[]','[]','{}','','',1000,1)"
        )
        connection.commit()
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS, "security-test").apply(connection)

        identity = connection.execute(
            "SELECT kind,organization_id,enabled,attributes_json FROM access_identities "
            "WHERE identity_id='fieldora-native-updater'"
        ).fetchone()
        extra_policies = connection.execute(
            "SELECT COUNT(*) FROM access_policies WHERE subject_id='fieldora-native-updater' "
            "AND policy_id<>'fieldora-native-updater-security-install'"
        ).fetchone()[0]
        roles = connection.execute(
            "SELECT COUNT(*) FROM access_role_assignments WHERE subject_id='fieldora-native-updater'"
        ).fetchone()[0]
        groups = connection.execute(
            "SELECT COUNT(*) FROM access_group_members WHERE member_id='fieldora-native-updater' "
            "OR group_id='fieldora-native-updater'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert identity == ("service", "", 1, "{}")
    assert extra_policies == 0
    assert roles == 0
    assert groups == 0


def test_existing_migration_7_database_upgrades_without_checksum_rewrite(tmp_path: Path) -> None:
    assert ACCESS_CONTROL_MIGRATIONS[6].checksum == (
        "5642fcd9073ffa621fd3930ab6a27e75dc3187e8fc678d3a104704a3a9c6ad86"
    )
    database = tmp_path / "access-control.sqlite3"
    connection = sqlite3.connect(database)
    try:
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS[:7], "security-test-old").apply(connection)
        connection.execute(
            "UPDATE access_identities SET organization_id='legacy-org',attributes_json='{\"platform_admin\":\"true\"}' "
            "WHERE identity_id='fieldora-native-updater'"
        )
        connection.execute(
            "INSERT INTO access_policies(policy_id,name,effect,source,source_id,subject_id,role_id," 
            "actions_json,resource_types_json,resource_id,organization_id,project_id,purposes_json," 
            "fields_json,conditions_json,valid_from_utc,valid_until_utc,priority,enabled) VALUES(" 
            "'post-v7-updater-admin','Post-v7 updater admin','allow','direct','legacy','fieldora-native-updater',''," 
            "'[\"*\"]','[\"*\"]','','','','[]','[]','{}','','',1000,1)"
        )
        connection.commit()

        MigrationRunner(ACCESS_CONTROL_MIGRATIONS, "security-test-current").apply(connection)

        migration_numbers = [
            row[0]
            for row in connection.execute(
                "SELECT migration_number FROM schema_migrations ORDER BY migration_number"
            )
        ]
        identity = connection.execute(
            "SELECT kind,organization_id,enabled,attributes_json FROM access_identities "
            "WHERE identity_id='fieldora-native-updater'"
        ).fetchone()
        extra_policies = connection.execute(
            "SELECT COUNT(*) FROM access_policies WHERE subject_id='fieldora-native-updater' "
            "AND policy_id<>'fieldora-native-updater-security-install'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert migration_numbers == list(range(1, 9))
    assert identity == ("service", "", 1, "{}")
    assert extra_policies == 0
