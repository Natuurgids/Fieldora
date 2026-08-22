"""Aperture Maintenance Center launcher with pre-GUI diagnostics."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from natureai_next.application.jobs import JobService
from natureai_next.application.library import LibraryLayout
from natureai_next.application.maintenance_inventory import MaintenanceInventoryReader
from natureai_next.application.retention import WorkflowCleanupService
from natureai_next.bootstrap.container import build_foundation_container
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.infrastructure.database.integrity import check_integrity
from natureai_next.infrastructure.database.job_commands import SqliteJobCommandStore
from natureai_next.infrastructure.database.restore import (
    replace_database_with_retry,
    validate_database_and_close,
)
from natureai_next.infrastructure.database.retention import SqliteRetentionHistoryStore
from natureai_next.infrastructure.filesystem.library_lock import _process_is_alive, _read_owner
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend
from natureai_next.infrastructure.maintenance_inventory import SqliteMaintenanceInventoryReader
from natureai_next.infrastructure.subsystems.maps import OfflineMapCatalog, OfflineMapPackageService
from natureai_next.ports.library_lifecycle import configure_default_library_backend
from natureai_next.ports.maintenance_platform import MaintenancePlatform


def _bootstrap_log(status: str, detail: str = "") -> None:
    log_dir = resolve_application_paths().logs_dir
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": status,
            "detail": detail,
        }
        with (log_dir / "maintenance-bootstrap.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        pass


def main(argv: Sequence[str] | None = None) -> int:
    configure_default_library_backend(
        lambda clock, ids, settings: SqliteLibraryLifecycleBackend(clock, ids, settings)
    )
    _bootstrap_log("process-started")
    try:
        from natureai_next.ui.qt.maintenance_center import main as qt_main

        _bootstrap_log("qt-imported")

        def inventory_reader_factory(library: Path) -> MaintenanceInventoryReader:
            container = build_foundation_container()
            paths = container.paths
            application_storage = (
                ("models", "Installed AI models", paths.models_dir, False),
                ("maps", "Offline map packages", paths.offline_map_packages_dir, False),
                ("taxonomy", "Taxonomy packages", paths.taxonomy_packages_dir, False),
                (
                    "subsystems", "Authoritative subsystem databases",
                    paths.subsystem_databases_dir, True,
                ),
                ("logs", "Application logs", paths.logs_dir, False),
                ("application_cache", "Application cache", paths.cache_dir, False),
            )
            return SqliteMaintenanceInventoryReader(
                layout=LibraryLayout.at(library),
                application_storage=application_storage,
                subsystem_registry=container.subsystem_registry,
            )

        def cleanup_service_factory(
            factory: object, roots: tuple[Path, ...]
        ) -> WorkflowCleanupService:
            return WorkflowCleanupService(SqliteRetentionHistoryStore(factory), roots)

        def job_service_factory(factory: object) -> JobService:
            container = build_foundation_container()
            return JobService(
                SqliteJobCommandStore(factory), container.clock, container.uuid_generator
            )

        result = qt_main(
            argv,
            inventory_reader_factory=inventory_reader_factory,
            cleanup_service_factory=cleanup_service_factory,
            job_service_factory=job_service_factory,
            platform=MaintenancePlatform(
                foundation_factory=build_foundation_container,
                map_catalog_factory=OfflineMapCatalog,
                map_package_service_factory=OfflineMapPackageService,
                vector_map_converter_factory=lambda: __import__(
                    "natureai_next.bootstrap.map_converter",
                    fromlist=["create_packaged_tilemaker_converter"],
                ).create_packaged_tilemaker_converter(),
                integrity_checker=lambda factory, full: check_integrity(factory, full=full),
                validate_database=validate_database_and_close,
                replace_database=replace_database_with_retry,
                read_lock_owner=_read_owner,
                process_is_alive=_process_is_alive,
            ),
        )
        _bootstrap_log("process-exited", str(result))
        return result
    except BaseException as exc:
        _bootstrap_log("bootstrap-failed", f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
