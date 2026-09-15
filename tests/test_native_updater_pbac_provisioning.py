from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import MigrationRunner
from natureai_next.infrastructure.subsystems.access_control import ACCESS_CONTROL_MIGRATIONS


def _provision(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS, "security-test").apply(connection)
    finally:
        connection.close()


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
