import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from natureai_next.bootstrap.retention_cli import main


def _run(arguments: list[str]):
    output = io.StringIO()
    with redirect_stdout(output):
        status = main(arguments)
    return status, json.loads(output.getvalue())


def test_retention_cli_enforces_hold_and_fenced_completion(tmp_path: Path) -> None:
    database = tmp_path / "retention.sqlite3"
    base = ["--database", str(database)]
    assert _run(
        base
        + [
            "register",
            "--organization",
            "tenant-a",
            "--resource-type",
            "export",
            "--resource-id",
            "export-1",
            "--expires-at-epoch",
            "100",
        ]
    )[0] == 0
    assert _run(
        base
        + [
            "hold-place",
            "--hold-id",
            "hold-1",
            "--organization",
            "tenant-a",
            "--reason",
            "investigation",
            "--created-at-epoch",
            "90",
        ]
    )[0] == 0
    status, claimed = _run(
        base + ["claim", "--worker-id", "worker-1", "--now-epoch", "101"]
    )
    assert status == 0 and claimed == []
    assert _run(
        base
        + [
            "hold-release",
            "--hold-id",
            "hold-1",
            "--released-at-epoch",
            "102",
        ]
    )[0] == 0
    _, claimed = _run(
        base + ["claim", "--worker-id", "worker-1", "--now-epoch", "103"]
    )
    candidate = claimed[0]
    status, result = _run(
        base
        + [
            "complete",
            "--worker-id",
            "worker-1",
            "--organization",
            candidate["organization_id"],
            "--resource-type",
            candidate["resource_type"],
            "--resource-id",
            candidate["resource_id"],
            "--expires-at-epoch",
            str(candidate["expires_at_epoch"]),
            "--lease-token",
            str(candidate["lease_token"]),
            "--removed-at-epoch",
            "104",
        ]
    )
    assert status == 0 and result["completed"] is True


def test_postgres_retention_claim_uses_skip_locked() -> None:
    root = Path(__file__).parents[1]
    source = (root / "src/natureai_next/server/postgres_retention.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "lease_token=r.lease_token+1" in source
    assert "NOT EXISTS(" in source
    assert "legal_holds" in source
