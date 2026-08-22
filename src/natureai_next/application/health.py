"""Library health assessment and conservative repair orchestration."""

from __future__ import annotations

import contextlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from natureai_next.application.library import LibraryLayout
from natureai_next.application.recovery import LibraryRecoveryService
from natureai_next.application.updates import UpdateSettingsStore
from natureai_next.domain.subsystems import SubsystemState
from natureai_next.ports.health import (
    ConnectionFactory,
    IntegrityReportView,
    SubsystemHealthRegistry,
)


class HealthSeverity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    key: str
    title: str
    severity: HealthSeverity
    summary: str
    detail: str = ""
    repairable: bool = False


@dataclass(frozen=True, slots=True)
class HealthReport:
    generated_at_utc: str
    checks: tuple[HealthCheck, ...]

    @property
    def healthy(self) -> bool:
        return not any(item.severity is HealthSeverity.ERROR for item in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(item.severity is HealthSeverity.WARNING for item in self.checks)

    @property
    def error_count(self) -> int:
        return sum(item.severity is HealthSeverity.ERROR for item in self.checks)


@dataclass(frozen=True, slots=True)
class RepairResult:
    repaired: tuple[str, ...]
    skipped: tuple[str, ...]


class LibraryHealthService:
    """Assess authoritative library state and perform only rebuild-safe repairs."""

    def __init__(
        self,
        *,
        layout: LibraryLayout,
        connection_factory: ConnectionFactory,
        integrity_checker: Callable[[ConnectionFactory, bool], IntegrityReportView],
        update_settings_path: Path,
        recovery_service: LibraryRecoveryService | None = None,
        subsystem_registry: SubsystemHealthRegistry | None = None,
        capability_registry: object | None = None,
    ) -> None:
        self._layout = layout
        self._factory = connection_factory
        self._integrity_checker = integrity_checker
        self._update_settings_path = update_settings_path
        self._recovery = recovery_service or LibraryRecoveryService()
        self._subsystems = subsystem_registry
        self._capabilities = capability_registry

    def assess(self, *, full_database_check: bool = False) -> HealthReport:
        checks: list[HealthCheck] = []
        checks.append(self._database_check(full=full_database_check))
        checks.append(self._manifest_check())
        checks.extend(self._directory_checks())
        checks.append(self._storage_check())
        checks.append(self._backup_check())
        checks.append(self._update_check())
        checks.append(self._temporary_files_check())
        checks.append(self._derived_data_check())
        checks.append(self._jobs_check())
        checks.extend(self._subsystem_checks())
        checks.append(self._capability_check())
        checks.append(self._analysis_integrity_check())
        return HealthReport(datetime.now(UTC).isoformat(), tuple(checks))

    def repair_safe_items(self) -> RepairResult:
        repaired: list[str] = []
        skipped: list[str] = []
        required = (
            self._layout.managed_originals,
            self._layout.sidecars,
            self._layout.thumbnails,
            self._layout.previews,
            self._layout.vector_indexes,
            self._layout.backups,
            self._layout.temp,
        )
        for path in required:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                repaired.append(f"Created {path.relative_to(self._layout.root)}")
        for candidate in self._layout.temp.glob("**/*") if self._layout.temp.exists() else ():
            if candidate.is_file() and candidate.suffix.casefold() in {".tmp", ".part"}:
                try:
                    candidate.unlink()
                    repaired.append(f"Removed stale temporary file {candidate.name}")
                except OSError:
                    skipped.append(f"Could not remove {candidate}")
        if not repaired:
            skipped.append("No safe repairs were needed")
        return RepairResult(tuple(repaired), tuple(skipped))

    def _database_check(self, *, full: bool) -> HealthCheck:
        try:
            report = self._integrity_checker(self._factory, full)
        except Exception as exc:
            return HealthCheck(
                "database",
                "Library database",
                HealthSeverity.ERROR,
                "Integrity check failed",
                str(exc),
            )
        if report.healthy:
            mode = "full" if full else "quick"
            return HealthCheck(
                "database",
                "Library database",
                HealthSeverity.OK,
                f"SQLite {mode} integrity check passed",
            )
        return HealthCheck(
            "database",
            "Library database",
            HealthSeverity.ERROR,
            "Database integrity problems detected",
            f"Checks: {report.quick_check}; foreign-key violations: {len(report.foreign_key_violations)}",
        )

    def _manifest_check(self) -> HealthCheck:
        if not self._layout.manifest.is_file():
            return HealthCheck(
                "manifest", "Library identity", HealthSeverity.ERROR, "library.json is missing"
            )
        try:
            payload = json.loads(self._layout.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return HealthCheck(
                "manifest",
                "Library identity",
                HealthSeverity.ERROR,
                "library.json is unreadable",
                str(exc),
            )
        if not payload.get("library_public_id") or not payload.get("display_name"):
            return HealthCheck(
                "manifest",
                "Library identity",
                HealthSeverity.ERROR,
                "Library manifest is incomplete",
            )
        return HealthCheck(
            "manifest",
            "Library identity",
            HealthSeverity.OK,
            f"{payload.get('display_name')} identity is readable",
        )

    def _directory_checks(self) -> tuple[HealthCheck, ...]:
        required = {
            "Originals": self._layout.managed_originals,
            "Sidecars": self._layout.sidecars,
            "Thumbnail cache": self._layout.thumbnails,
            "Preview cache": self._layout.previews,
            "Vector indexes": self._layout.vector_indexes,
            "Backups": self._layout.backups,
            "Temporary workspace": self._layout.temp,
        }
        missing = [name for name, path in required.items() if not path.is_dir()]
        if missing:
            return (
                HealthCheck(
                    "directories",
                    "Library folders",
                    HealthSeverity.WARNING,
                    f"{len(missing)} required folder(s) are missing",
                    ", ".join(missing),
                    repairable=True,
                ),
            )
        return (
            HealthCheck(
                "directories",
                "Library folders",
                HealthSeverity.OK,
                "All required library folders are present",
            ),
        )

    def _storage_check(self) -> HealthCheck:
        try:
            usage = shutil.disk_usage(self._layout.root)
            free_gib = usage.free / (1024**3)
        except OSError as exc:
            return HealthCheck(
                "storage",
                "Storage",
                HealthSeverity.ERROR,
                "Storage availability could not be read",
                str(exc),
            )
        writable = self._layout.root.is_dir() and os_access_write(self._layout.root)
        if not writable:
            return HealthCheck(
                "storage", "Storage", HealthSeverity.ERROR, "Library folder is not writable"
            )
        if free_gib < 1.0:
            return HealthCheck(
                "storage", "Storage", HealthSeverity.ERROR, f"Only {free_gib:.2f} GiB is free"
            )
        if free_gib < 5.0:
            return HealthCheck(
                "storage", "Storage", HealthSeverity.WARNING, f"Low free space: {free_gib:.1f} GiB"
            )
        return HealthCheck(
            "storage",
            "Storage",
            HealthSeverity.OK,
            f"{free_gib:.1f} GiB free and library is writable",
        )

    def _backup_check(self) -> HealthCheck:
        backups = self._recovery.list_backups(self._layout.backups)
        if not backups:
            return HealthCheck(
                "backups",
                "Verified backups",
                HealthSeverity.WARNING,
                "No verified database backup was found",
            )
        latest = backups[0]
        try:
            created = datetime.fromisoformat(latest.created_at_utc.replace("Z", "+00:00"))
            age_days = (datetime.now(UTC) - created.astimezone(UTC)).days
        except ValueError:
            age_days = 9999
        if age_days > 30:
            return HealthCheck(
                "backups",
                "Verified backups",
                HealthSeverity.WARNING,
                f"Latest verified backup is {age_days} days old",
            )
        return HealthCheck(
            "backups",
            "Verified backups",
            HealthSeverity.OK,
            f"{len(backups)} verified backup(s); latest is {age_days} day(s) old",
        )

    def _update_check(self) -> HealthCheck:
        settings = UpdateSettingsStore().load(self._update_settings_path)
        if settings is None or settings.source is None:
            return HealthCheck(
                "updates",
                "Offline updates",
                HealthSeverity.WARNING,
                "No update source is configured",
            )
        if not settings.source.exists():
            return HealthCheck(
                "updates",
                "Offline updates",
                HealthSeverity.WARNING,
                "Configured update source is unavailable",
                str(settings.source),
            )
        return HealthCheck(
            "updates",
            "Offline updates",
            HealthSeverity.OK,
            f"Update source is available: {settings.source}",
        )

    def _temporary_files_check(self) -> HealthCheck:
        stale = (
            tuple(
                path
                for path in self._layout.temp.glob("**/*")
                if path.is_file() and path.suffix.casefold() in {".tmp", ".part"}
            )
            if self._layout.temp.exists()
            else ()
        )
        if stale:
            return HealthCheck(
                "temporary",
                "Temporary files",
                HealthSeverity.WARNING,
                f"{len(stale)} stale temporary file(s) found",
                repairable=True,
            )
        return HealthCheck(
            "temporary", "Temporary files", HealthSeverity.OK, "No stale temporary files found"
        )

    def _derived_data_check(self) -> HealthCheck:
        missing = []
        if not self._layout.thumbnails.exists():
            missing.append("thumbnail cache")
        if not self._layout.previews.exists():
            missing.append("preview cache")
        if not self._layout.vector_indexes.exists():
            missing.append("vector indexes")
        if missing:
            return HealthCheck(
                "derived",
                "Rebuildable data",
                HealthSeverity.WARNING,
                "Some rebuildable stores are absent",
                ", ".join(missing),
                repairable=True,
            )
        return HealthCheck(
            "derived",
            "Rebuildable data",
            HealthSeverity.OK,
            "Cache and index locations are available",
        )

    def _jobs_check(self) -> HealthCheck:
        try:
            connection = self._factory.connect(read_only=True)
            try:
                rows = connection.execute(
                    "SELECT state, COUNT(*) AS count FROM jobs GROUP BY state"
                ).fetchall()
            finally:
                connection.close()
        except Exception as exc:
            return HealthCheck(
                "jobs",
                "Background work",
                HealthSeverity.ERROR,
                "Job status could not be read",
                str(exc),
            )
        counts = {str(row["state"]): int(row["count"]) for row in rows}
        active = sum(
            counts.get(state, 0) for state in ("queued", "running", "paused", "interrupted")
        )
        failed = counts.get("failed", 0)
        if failed:
            return HealthCheck(
                "jobs",
                "Background work",
                HealthSeverity.WARNING,
                f"{active} active or resumable job(s); {failed} failed job(s)",
                "Use the Maintenance Center stop/continue controls to inspect and resume or cancel work.",
            )
        return HealthCheck(
            "jobs",
            "Background work",
            HealthSeverity.OK,
            f"{active} active or resumable job(s); no failed jobs",
        )

    def _subsystem_checks(self) -> tuple[HealthCheck, ...]:
        if self._subsystems is None:
            return ()
        checks: list[HealthCheck] = []
        for key in self._subsystems.keys():
            status = self._subsystems.status(key, run_integrity_check=True)
            title = f"Optional subsystem: {key}"
            if status.state is SubsystemState.UNAVAILABLE:
                checks.append(
                    HealthCheck(
                        f"subsystem:{key}",
                        title,
                        HealthSeverity.WARNING,
                        "Installed subsystem database is unavailable",
                        status.message,
                    )
                )
            elif status.state is SubsystemState.UNHEALTHY:
                checks.append(
                    HealthCheck(
                        f"subsystem:{key}",
                        title,
                        HealthSeverity.ERROR,
                        "Subsystem database integrity problems detected",
                        status.message,
                    )
                )
            elif (
                status.schema_version
                and status.schema_version != self._subsystems.descriptor(key).schema_version
            ):
                checks.append(
                    HealthCheck(
                        f"subsystem:{key}",
                        title,
                        HealthSeverity.WARNING,
                        f"Schema version {status.schema_version} is not current",
                    )
                )
            elif status.database_path.exists():
                checks.append(
                    HealthCheck(
                        f"subsystem:{key}",
                        title,
                        HealthSeverity.OK,
                        f"Available; schema version {status.schema_version}",
                    )
                )
            else:
                checks.append(
                    HealthCheck(
                        f"subsystem:{key}",
                        title,
                        HealthSeverity.OK,
                        "Not installed or activated; core library is unaffected",
                    )
                )
        return tuple(checks)

    def _capability_check(self) -> HealthCheck:
        if self._capabilities is None:
            return HealthCheck(
                "capabilities",
                "Capability registry",
                HealthSeverity.OK,
                "No optional capability registry was supplied",
            )
        try:
            keys = tuple(self._capabilities.keys())
        except Exception as exc:
            return HealthCheck(
                "capabilities",
                "Capability registry",
                HealthSeverity.ERROR,
                "Capability registration could not be read",
                str(exc),
            )
        return HealthCheck(
            "capabilities",
            "Capability registry",
            HealthSeverity.OK,
            f"{len(keys)} optional capability definition(s) registered lazily",
        )

    def _analysis_integrity_check(self) -> HealthCheck:
        try:
            connection = self._factory.connect(read_only=True)
            try:
                orphan_analyses = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM asset_analyses a LEFT JOIN assets x ON x.id=a.asset_id WHERE x.id IS NULL"
                    ).fetchone()[0]
                )
                orphan_candidates = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM analysis_taxon_candidates c LEFT JOIN asset_analyses a ON a.id=c.analysis_id WHERE a.id IS NULL"
                    ).fetchone()[0]
                )
            finally:
                connection.close()
        except Exception as exc:
            return HealthCheck(
                "analyses",
                "Asset enrichment",
                HealthSeverity.WARNING,
                "Analysis consistency could not be assessed",
                str(exc),
            )
        total = orphan_analyses + orphan_candidates
        if total:
            return HealthCheck(
                "analyses",
                "Asset enrichment",
                HealthSeverity.ERROR,
                f"{total} orphan analysis record(s) detected",
            )
        return HealthCheck(
            "analyses",
            "Asset enrichment",
            HealthSeverity.OK,
            "Asset analyses and candidates have valid parent records",
        )


def os_access_write(path: Path) -> bool:
    """Check practical directory write access without leaving an artifact behind."""
    probe = path / ".aperture-health-write-test.tmp"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        with contextlib.suppress(OSError):
            probe.unlink(missing_ok=True)
        return False
