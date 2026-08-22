import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from natureai_next.bootstrap.secret_rotation_cli import main


def _run(arguments: list[str]):
    output = io.StringIO()
    with redirect_stdout(output):
        status = main(arguments)
    return status, json.loads(output.getvalue())


def test_secret_rotation_cli_requires_expected_active_version(tmp_path: Path) -> None:
    database = tmp_path / "rotation.sqlite3"
    base = ["--database", str(database)]
    assert _run(
        base
        + [
            "stage",
            "--purpose",
            "oidc-signing",
            "--version-id",
            "v1",
            "--provider-reference",
            "vault://fieldora/oidc/v1",
            "--created-at-epoch",
            "100",
        ]
    )[0] == 0
    status, active = _run(
        base
        + [
            "activate",
            "--purpose",
            "oidc-signing",
            "--version-id",
            "v1",
            "--activated-at-epoch",
            "101",
        ]
    )
    assert status == 0 and active["version_id"] == "v1"
    assert _run(
        base
        + [
            "stage",
            "--purpose",
            "oidc-signing",
            "--version-id",
            "v2",
            "--provider-reference",
            "external-secret://fieldora/oidc/v2",
            "--created-at-epoch",
            "102",
        ]
    )[0] == 0
    with pytest.raises(ValueError, match="active_version_conflict"):
        main(
            base
            + [
                "activate",
                "--purpose",
                "oidc-signing",
                "--version-id",
                "v2",
                "--activated-at-epoch",
                "103",
                "--expected-active-version",
                "wrong",
            ]
        )
    status, active = _run(
        base
        + [
            "activate",
            "--purpose",
            "oidc-signing",
            "--version-id",
            "v2",
            "--activated-at-epoch",
            "104",
            "--expected-active-version",
            "v1",
        ]
    )
    assert status == 0 and active["version_id"] == "v2"
    _, report = _run(base + ["status", "--purpose", "oidc-signing"])
    assert report["active"]["provider_reference"].startswith("external-secret://")
    assert [row["state"] for row in report["versions"]] == ["retired", "active"]


def test_postgres_rotation_serializes_each_purpose() -> None:
    source = (
        Path(__file__).parents[1]
        / "src/natureai_next/server/postgres_secret_rotation.py"
    ).read_text()
    assert "pg_advisory_xact_lock" in source
    assert "FOR UPDATE" in source
    assert "expected_active_version" in source
