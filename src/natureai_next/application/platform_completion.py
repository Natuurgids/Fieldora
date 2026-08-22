"""Read-only platform completion diagnostics for Aperture Build 35.

The reader deliberately avoids opening the application through its normal write-capable
bootstrap.  It can therefore be used by Maintenance Center while Aperture is closed and
produces a portable, privacy-conscious support snapshot.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BackupAudit:
    file: str
    manifest: str | None
    size_bytes: int
    sha256_matches: bool | None
    sqlite_integrity: str


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    workflow_id: str
    run_key: str
    total_steps: int
    states: dict[str, int]
    latest_modified_at_us: int


@dataclass(frozen=True, slots=True)
class PlatformSnapshot:
    format: str
    version: int
    generated_at_utc: str
    aperture_version: str
    library_name: str
    library_public_id: str
    python: str
    operating_system: str
    database_integrity: str
    database_size_bytes: int
    job_states: dict[str, int]
    workflow_runs: tuple[WorkflowSummary, ...]
    backups: tuple[BackupAudit, ...]
    storage: dict[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


class PlatformSnapshotReader:
    """Capture health, workflow, backup and storage status without mutating a library."""

    def __init__(self, library: Path, *, aperture_version: str = "unknown") -> None:
        self.library = Path(library).expanduser().resolve()
        self.aperture_version = aperture_version

    def capture(self) -> PlatformSnapshot:
        manifest = self._manifest()
        database = self.library / "library.sqlite3"
        integrity, job_states, workflows = self._database_snapshot(database)
        return PlatformSnapshot(
            format="aperture.platform-snapshot",
            version=1,
            generated_at_utc=datetime.now(UTC).isoformat(),
            aperture_version=self.aperture_version,
            library_name=str(manifest.get("display_name") or self.library.name),
            library_public_id=str(manifest.get("library_public_id") or "unknown"),
            python=platform.python_version(),
            operating_system=f"{platform.system()} {platform.release()}",
            database_integrity=integrity,
            database_size_bytes=database.stat().st_size if database.is_file() else 0,
            job_states=job_states,
            workflow_runs=workflows,
            backups=self._backups(),
            storage=self._storage(),
        )

    def write(self, destination: Path) -> Path:
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".tmp")
        temp.write_text(self.capture().to_json(), encoding="utf-8")
        temp.replace(destination)
        return destination

    def _manifest(self) -> dict[str, Any]:
        path = self.library / "library.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @staticmethod
    def _database_snapshot(database: Path) -> tuple[str, dict[str, int], tuple[WorkflowSummary, ...]]:
        if not database.is_file():
            return "missing", {}, ()
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            integrity = str(row[0]) if row else "unknown"
            tables = {str(item[0]) for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "jobs" not in tables:
                return integrity, {}, ()
            states = {str(row["state"]): int(row["count"]) for row in connection.execute("SELECT state, COUNT(*) count FROM jobs GROUP BY state")}
            runs: dict[tuple[str, str], dict[str, Any]] = {}
            for row in connection.execute("SELECT payload_json,state,modified_at_us FROM jobs ORDER BY modified_at_us DESC"):
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except (ValueError, TypeError):
                    continue
                workflow_id = payload.get("workflow_id")
                run_key = payload.get("workflow_run_key")
                if not workflow_id or not run_key:
                    continue
                key = (str(workflow_id), str(run_key))
                run = runs.setdefault(key, {"states": {}, "total": 0, "latest": 0})
                state = str(row["state"])
                run["states"][state] = run["states"].get(state, 0) + 1
                run["total"] += 1
                run["latest"] = max(run["latest"], int(row["modified_at_us"] or 0))
            summaries = tuple(
                WorkflowSummary(key[0], key[1], value["total"], value["states"], value["latest"])
                for key, value in sorted(runs.items(), key=lambda item: item[1]["latest"], reverse=True)
            )
            return integrity, states, summaries[:100]
        finally:
            connection.close()

    def _backups(self) -> tuple[BackupAudit, ...]:
        backup_dir = self.library / "backups"
        result: list[BackupAudit] = []
        for path in sorted(backup_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True):
            manifest_path = path.with_suffix(path.suffix + ".manifest.json")
            expected: str | None = None
            if manifest_path.is_file():
                try:
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    expected = str(payload.get("sha256") or "") or None
                except (OSError, ValueError, TypeError):
                    pass
            actual = self._digest(path) if expected else None
            try:
                con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
                row = con.execute("PRAGMA quick_check").fetchone()
                integrity = str(row[0]) if row else "unknown"
                con.close()
            except sqlite3.Error as exc:
                integrity = f"error: {exc}"
            result.append(BackupAudit(path.name, manifest_path.name if manifest_path.is_file() else None, path.stat().st_size, actual == expected if expected else None, integrity))
        return tuple(result)

    def _storage(self) -> dict[str, int]:
        categories = {
            "managed_originals_bytes": self.library / "originals",
            "cache_bytes": self.library / "cache",
            "backups_bytes": self.library / "backups",
            "temporary_bytes": self.library / "temp",
        }
        return {name: self._tree_size(path) for name, path in categories.items()}

    @staticmethod
    def _tree_size(root: Path) -> int:
        total = 0
        if not root.exists():
            return total
        for base, _dirs, files in os.walk(root):
            for name in files:
                try:
                    total += (Path(base) / name).stat().st_size
                except OSError:
                    continue
        return total

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
