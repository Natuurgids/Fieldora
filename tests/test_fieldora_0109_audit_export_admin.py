import io
import json
import sqlite3
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from natureai_next.bootstrap.audit_export_cli import main
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


def _event(organization: str, action: str) -> dict:
    return {
        "occurred_at_utc": "2026-07-29T12:00:00Z",
        "subject_id": "operator-1",
        "action": action,
        "resource_type": "project",
        "resource_id": "project-1",
        "allowed": True,
        "reason": "policy_allow",
        "policy_ids": ["policy-1"],
        "request": {
            "organization_id": organization,
            "project_id": "project-1",
            "purpose": "administration",
        },
    }


def test_cli_exports_only_verified_tenant_events(tmp_path: Path) -> None:
    database = tmp_path / "access.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.append_audit(_event("tenant-a", "read"))
    repository.append_audit(_event("tenant-b", "hidden"))
    destination = tmp_path / "tenant-a-audit.zip"
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(
            [
                "--database",
                str(database),
                "export",
                "--organization",
                "tenant-a",
                "--destination",
                str(destination),
            ]
        ) == 0
    result = json.loads(output.getvalue())
    assert result["manifest"]["source_chain_verified"] is True
    with zipfile.ZipFile(destination) as archive:
        exported = [
            json.loads(line)
            for line in archive.read("events.jsonl").decode().splitlines()
        ]
    assert len(exported) == 1
    assert exported[0]["organization_id"] == "tenant-a"


def test_cli_refuses_tampered_source_chain(tmp_path: Path) -> None:
    database = tmp_path / "access.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.append_audit(_event("tenant-a", "read"))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE access_audit_events SET reason='tampered' WHERE sequence=1"
        )
    with pytest.raises(ValueError, match="audit chain verification failed"):
        main(
            [
                "--database",
                str(database),
                "export",
                "--organization",
                "tenant-a",
                "--destination",
                str(tmp_path / "invalid.zip"),
            ]
        )
