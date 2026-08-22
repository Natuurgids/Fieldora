from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.enrichment import (
    CanonicalEnrichment,
    CanonicalEnrichmentService,
    EnrichmentLabel,
    EnrichmentValue,
)
from natureai_next.application.integrations import IntegrationRegistryService
from natureai_next.application.library_capabilities import LibraryCapabilityService
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


def _core_database(path: Path) -> None:
    connection = SqliteConnectionFactory(path).connect()
    try:
        MigrationRunner(CORE_MIGRATIONS, __version__).apply(connection)
    finally:
        connection.close()


def test_all_library_types_are_enabled_by_default(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite3"
    _core_database(database)
    service = LibraryCapabilityService(database)
    assert {item.capability_id: item.enabled for item in service.list()} == {
        "library.photos": True,
        "library.sounds": True,
        "library.videos": True,
        "library.documents": True,
    }
    service.set_enabled("library.videos", False)
    assert service.enabled("library.videos") is False


def test_media_types_have_independent_tables(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite3"
    _core_database(database)
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {
        "library_assets",
        "photo_assets",
        "sound_assets",
        "video_assets",
        "document_assets",
    } <= tables


def test_integrations_can_be_disabled_without_removing_registry_data(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite3"
    _core_database(database)
    service = IntegrationRegistryService(database)
    service.set_enabled("natureai.next", False)
    natureai = next(item for item in service.list() if item.integration_id == "natureai.next")
    assert natureai.enabled is False
    assert "suggestions" in natureai.capabilities


def test_canonical_enrichment_is_in_independent_database(tmp_path: Path) -> None:
    core = tmp_path / "library.sqlite3"
    enrichment = tmp_path / "subsystems" / "enrichment.sqlite3"
    _core_database(core)
    registry = SubsystemDatabaseRegistry((enrichment_descriptor(enrichment),), __version__)
    registry.activate("enrichment")
    service = CanonicalEnrichmentService(enrichment)
    service.store(
        CanonicalEnrichment(
            enrichment_id="enr-1",
            subject_type="asset",
            subject_public_id="asset-1",
            enrichment_type="biological.species_candidate",
            producer_id="example.plugin",
            values=(EnrichmentValue("species.scientific_name", "Vulpes vulpes", "text"),),
            labels=(EnrichmentLabel("organism-group", "mammal", "Mammal"),),
        )
    )
    with sqlite3.connect(enrichment) as connection:
        assert (
            connection.execute(
                "SELECT producer_id FROM enrichment_records WHERE enrichment_id='enr-1'"
            ).fetchone()[0]
            == "example.plugin"
        )
    with sqlite3.connect(core) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='enrichment_records'"
            ).fetchone()
            is None
        )
