import json
import zipfile
from pathlib import Path

from natureai_next.server.audit_export import (
    export_tenant_audit,
    verify_tenant_audit_export,
)
from natureai_next.server.retention import RetentionStore


def test_legal_hold_blocks_retention_until_released(tmp_path: Path) -> None:
    store = RetentionStore(tmp_path / "retention.sqlite3")
    store.register("tenant-a", "export", "export-1", 100)
    store.place_hold("hold-1", "tenant-a", "investigation", 50)
    assert store.claim_due("worker-a", 101) == ()
    assert store.release_hold("hold-1", 102)
    claimed = store.claim_due("worker-a", 103)
    assert len(claimed) == 1
    assert store.complete_removal(claimed[0], "worker-a", 104)


def test_stale_retention_worker_cannot_complete_removal(tmp_path: Path) -> None:
    store = RetentionStore(tmp_path / "retention.sqlite3")
    store.register("tenant-a", "media", "media-1", 100)
    stale = store.claim_due("worker-a", 101, lease_seconds=5)[0]
    current = store.claim_due("worker-b", 107, lease_seconds=5)[0]
    assert not store.complete_removal(stale, "worker-a", 108)
    assert store.complete_removal(current, "worker-b", 108)


def test_audit_export_is_tenant_scoped_and_detects_tampering(tmp_path: Path) -> None:
    events = (
        {"sequence": 2, "organization_id": "tenant-b", "action": "hidden"},
        {"sequence": 1, "organization_id": "tenant-a", "action": "view"},
    )
    destination = export_tenant_audit(events, "tenant-a", tmp_path / "audit.zip")
    manifest = verify_tenant_audit_export(destination)
    assert manifest["event_count"] == 1
    with zipfile.ZipFile(destination) as archive:
        exported = json.loads(archive.read("events.jsonl"))
    assert exported["organization_id"] == "tenant-a"
