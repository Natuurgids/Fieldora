"""Bootstrap composition for optional subsystem database adapters."""

from __future__ import annotations

from natureai_next import __version__
from natureai_next.bootstrap.paths import ApplicationPaths
from natureai_next.infrastructure.database.settings import SqliteSettings
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.maps import maps_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.infrastructure.subsystems.science import science_descriptor
from natureai_next.infrastructure.subsystems.server_media import server_media_descriptor
from natureai_next.infrastructure.subsystems.server_search import server_search_descriptor
from natureai_next.infrastructure.subsystems.server_jobs import server_jobs_descriptor
from natureai_next.infrastructure.subsystems.server_exports import server_exports_descriptor
from natureai_next.infrastructure.subsystems.access_control import (
    access_control_descriptor,
)
from natureai_next.infrastructure.subsystems.taxonomy import taxonomy_descriptor


def build_subsystem_registry(
    paths: ApplicationPaths,
    settings: SqliteSettings | None = None,
) -> SubsystemDatabaseRegistry:
    """Compose map and taxonomy adapters without activating either database."""
    return SubsystemDatabaseRegistry(
        (
            enrichment_descriptor(paths.subsystem_databases_dir / "enrichment.sqlite3"),
            maps_descriptor(paths.subsystem_databases_dir / "maps-offline.sqlite3"),
            taxonomy_descriptor(paths.subsystem_databases_dir / "taxonomy-reference.sqlite3"),
            science_descriptor(paths.subsystem_databases_dir / "science.sqlite3"),
            access_control_descriptor(
                paths.subsystem_databases_dir / "access-control.sqlite3"
            ),
            server_media_descriptor(
                paths.subsystem_databases_dir / "server-media.sqlite3"
            ),
            server_search_descriptor(
                paths.subsystem_databases_dir / "server-search.sqlite3"
            ),
            server_jobs_descriptor(
                paths.subsystem_databases_dir / "server-jobs.sqlite3"
            ),
            server_exports_descriptor(
                paths.subsystem_databases_dir / "server-exports.sqlite3"
            ),
        ),
        __version__,
        settings,
    )
