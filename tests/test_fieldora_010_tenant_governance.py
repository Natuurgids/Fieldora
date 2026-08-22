from pathlib import Path

from natureai_next.server.tenant_governance import SqliteTenantGovernance


def test_quota_consumption_is_atomic_and_resets_by_period(tmp_path: Path) -> None:
    governance = SqliteTenantGovernance(tmp_path / "governance.sqlite3")
    revision = governance.set_quota("tenant-a", "api_requests", 2, 60)
    assert revision == 1
    assert governance.consume("tenant-a", "api_requests", now_epoch=120).allowed
    second = governance.consume("tenant-a", "api_requests", now_epoch=121)
    assert second.allowed and second.remaining == 0
    denied = governance.consume("tenant-a", "api_requests", now_epoch=122)
    assert denied.allowed is False
    assert denied.used == 2
    assert denied.resets_at_epoch == 180
    assert governance.consume("tenant-a", "api_requests", now_epoch=180).allowed


def test_denied_usage_is_not_charged_and_report_is_tenant_scoped(tmp_path: Path) -> None:
    governance = SqliteTenantGovernance(tmp_path / "governance.sqlite3")
    governance.set_quota("tenant-a", "export_bytes", 10, 3600)
    assert governance.consume("tenant-a", "export_bytes", 8, now_epoch=100).allowed
    assert not governance.consume("tenant-a", "export_bytes", 3, now_epoch=101).allowed
    governance.consume("tenant-b", "export_bytes", 50, now_epoch=102)
    report = governance.usage_report("tenant-a", 0, 200)
    assert report == (
        {"organization_id": "tenant-a", "metric": "export_bytes", "amount": 8},
    )


def test_quota_updates_use_optimistic_revision(tmp_path: Path) -> None:
    governance = SqliteTenantGovernance(tmp_path / "governance.sqlite3")
    governance.set_quota("tenant-a", "jobs", 5, 60)
    try:
        governance.set_quota(
            "tenant-a", "jobs", 10, 60, expected_revision=0
        )
    except ValueError as exc:
        assert str(exc) == "revision_conflict"
    else:
        raise AssertionError("stale quota update was accepted")
    assert governance.set_quota(
        "tenant-a", "jobs", 10, 60, expected_revision=1
    ) == 2


def test_api_and_production_manifest_use_tenant_governance() -> None:
    root = Path(__file__).parents[1]
    api = (root / "src/natureai_next/server/api.py").read_text()
    manifest = (root / "deployment/kubernetes/base/platform.yaml").read_text()
    assert '"tenant_quota_exceeded"' in api
    assert "--governance-backend" in manifest
    assert "postgresql" in manifest
