from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from natureai_next.application.platform_completion import PlatformSnapshotReader


def _library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    (root / "backups").mkdir(parents=True)
    (root / "cache").mkdir()
    (root / "originals").mkdir()
    (root / "temp").mkdir()
    (root / "library.json").write_text(json.dumps({"display_name": "Field Library", "library_public_id": "lib-1"}), encoding="utf-8")
    con = sqlite3.connect(root / "library.sqlite3")
    con.execute("CREATE TABLE jobs(payload_json TEXT,state TEXT,modified_at_us INTEGER)")
    con.execute("INSERT INTO jobs VALUES(?,?,?)", (json.dumps({"workflow_id":"enrich","workflow_run_key":"run-1"}), "succeeded", 10))
    con.execute("INSERT INTO jobs VALUES(?,?,?)", (json.dumps({"workflow_id":"enrich","workflow_run_key":"run-1"}), "failed", 20))
    con.commit(); con.close()
    return root


def test_snapshot_captures_workflows_and_health(tmp_path: Path) -> None:
    root = _library(tmp_path)
    snapshot = PlatformSnapshotReader(root, aperture_version="4.0.0.dev1+build35").capture()
    assert snapshot.database_integrity == "ok"
    assert snapshot.job_states == {"failed": 1, "succeeded": 1}
    assert snapshot.workflow_runs[0].workflow_id == "enrich"
    assert snapshot.workflow_runs[0].total_steps == 2
    assert snapshot.library_public_id == "lib-1"


def test_snapshot_audits_backup_manifest(tmp_path: Path) -> None:
    root = _library(tmp_path)
    backup = root / "backups" / "good.sqlite3"
    con = sqlite3.connect(backup); con.execute("CREATE TABLE x(id INTEGER)"); con.commit(); con.close()
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    backup.with_suffix(".sqlite3.manifest.json").write_text(json.dumps({"sha256": digest}), encoding="utf-8")
    audit = PlatformSnapshotReader(root).capture().backups[0]
    assert audit.sha256_matches is True
    assert audit.sqlite_integrity == "ok"


def test_snapshot_write_is_atomic_and_json(tmp_path: Path) -> None:
    root = _library(tmp_path)
    target = tmp_path / "support" / "snapshot.json"
    PlatformSnapshotReader(root).write(target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["format"] == "aperture.platform-snapshot"
    assert not target.with_suffix(".json.tmp").exists()
