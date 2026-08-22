import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from natureai_next.bootstrap.governance_cli import main
from natureai_next.server.tenant_governance import (
    SqliteTenantGovernance,
    costed_usage_report,
)


def test_cost_report_uses_decimal_strings() -> None:
    report = costed_usage_report(
        (
            {"organization_id": "tenant-a", "metric": "export_bytes", "amount": 3},
        ),
        {"export_bytes": "0.125"},
    )
    assert report["items"][0]["cost"] == "0.375"
    assert report["total_cost"] == "0.375"


def test_governance_cli_sets_quota_and_reports_scoped_usage(tmp_path: Path) -> None:
    database = tmp_path / "governance.sqlite3"
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(
            [
                "--database",
                str(database),
                "quota-set",
                "--organization",
                "tenant-a",
                "--metric",
                "jobs",
                "--limit",
                "5",
                "--period-seconds",
                "3600",
            ]
        ) == 0
    assert json.loads(output.getvalue())["revision"] == 1
    repository = SqliteTenantGovernance(database)
    repository.consume("tenant-a", "jobs", 2, now_epoch=100)
    rates = tmp_path / "rates.json"
    rates.write_text('{"jobs":"1.50"}')
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(
            [
                "--database",
                str(database),
                "usage-report",
                "--organization",
                "tenant-a",
                "--start-epoch",
                "0",
                "--end-epoch",
                "200",
                "--unit-costs",
                str(rates),
            ]
        ) == 0
    report = json.loads(output.getvalue())
    assert report["items"][0]["amount"] == 2
    assert report["total_cost"] == "3.00"
