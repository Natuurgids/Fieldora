from __future__ import annotations

import json
from pathlib import Path

from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.enrichment_catalog import (
    EnrichmentCatalogService,
    EnrichmentSearchQuery,
)
from natureai_next.application.enrichment_projection import EnrichmentProjectionService
from natureai_next.application.observation_links import ObservationLinkService
from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceRemovalOptions,
    SourceState,
)
from natureai_next.application.source_workspace import SourceWorkspaceService
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.plugins.bundles import OfflineBundleRemover
from natureai_next.synthesis_core import CsvReferenceImporter, InProcessSourceRouter


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def test_csv_source_import_creates_pending_candidates_and_catalog_export(tmp_path: Path) -> None:
    database = _database(tmp_path)
    csv_file = tmp_path / "reference.csv"
    csv_file.write_text(
        "id,name,confidence\nsp-1,European robin,0.93\nsp-2,Blackbird,0.81\n", encoding="utf-8"
    )
    router = InProcessSourceRouter()
    router.register(CsvReferenceImporter())
    identifiers = iter(("csv-1", "csv-2"))
    service = SourceWorkspaceService(
        database, router, id_factory=lambda: next(identifiers), clock_us=lambda: 100
    )
    subject = SubjectRef(SubjectType.PHOTO, "photo-1")

    outcome = service.import_file(
        subject,
        source_id="org.aperture.csv-reference",
        input_path=csv_file,
        parameters={
            "shape": "label",
            "value_column": "name",
            "external_id_column": "id",
            "confidence_column": "confidence",
            "source_version": "2026-07",
            "licence": "CC0-1.0",
        },
    )
    assert outcome.created_enrichment_ids == ("csv-1", "csv-2")
    assert [item.summary for item in outcome.projection.pending] == ["European robin", "Blackbird"]

    store = CanonicalEnrichmentService(database)
    store.review("csv-1", EnrichmentStatus.ACCEPTED, reviewer="observer", reviewed_at_us=200)
    catalog = EnrichmentCatalogService(database)
    found = catalog.search(EnrichmentSearchQuery(text="robin", accepted_only=True))
    assert [item.enrichment_id for item in found] == ["csv-1"]
    report = catalog.report()
    assert report.total == 2
    assert report.by_status == {"accepted": 1, "pending_review": 1}
    exported = catalog.export_json(
        tmp_path / "accepted.json", EnrichmentSearchQuery(accepted_only=True)
    )
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert document["records"][0]["source_snapshot"]["licence"] == "CC0-1.0"


def test_observation_projection_discovers_linked_accepted_evidence(tmp_path: Path) -> None:
    database = _database(tmp_path)
    csv_file = tmp_path / "reference.csv"
    csv_file.write_text("value\nEuropean robin\n", encoding="utf-8")
    router = InProcessSourceRouter()
    router.register(CsvReferenceImporter())
    photo = SubjectRef(SubjectType.PHOTO, "photo-1")
    SourceWorkspaceService(
        database, router, id_factory=lambda: "enr-1", clock_us=lambda: 100
    ).import_file(
        photo,
        source_id="org.aperture.csv-reference",
        input_path=csv_file,
    )
    CanonicalEnrichmentService(database).review(
        "enr-1", EnrichmentStatus.ACCEPTED, reviewer="observer"
    )
    ObservationLinkService(database).link("obs-1", photo)

    view = EnrichmentProjectionService(database).for_observation("obs-1")
    assert len(view.accepted) == 1
    assert view.accepted[0].summary == "European robin"


def test_bundle_removal_deletes_files_but_preserves_accepted_enrichment(tmp_path: Path) -> None:
    database = _database(tmp_path)
    registry = SourceRegistryService(database)
    registry.register(
        SourceRecord("org.aperture.csv-reference", "source", "CSV", "1.0.0", SourceState.INSTALLED)
    )
    install_root = tmp_path / "installed"
    version_root = install_root / "org.aperture.csv-reference" / "1.0.0"
    version_root.mkdir(parents=True)
    (version_root / "source.csv").write_text("value\nrobin\n", encoding="utf-8")

    csv_file = tmp_path / "reference.csv"
    csv_file.write_text("value\nrobin\n", encoding="utf-8")
    router = InProcessSourceRouter()
    router.register(CsvReferenceImporter())
    SourceWorkspaceService(
        database, router, id_factory=lambda: "accepted", clock_us=lambda: 100
    ).import_file(
        SubjectRef(SubjectType.PHOTO, "photo-1"),
        source_id="org.aperture.csv-reference",
        input_path=csv_file,
    )
    CanonicalEnrichmentService(database).review(
        "accepted", EnrichmentStatus.ACCEPTED, reviewer="observer"
    )

    removed = OfflineBundleRemover(install_root, registry).remove(
        "org.aperture.csv-reference",
        SourceRemovalOptions(
            remove_runtime_files=True,
            remove_indexes_and_caches=True,
            delete_pending_results=True,
            delete_rejected_results=True,
            delete_accepted_enrichment=False,
        ),
    )
    assert removed == (install_root / "org.aperture.csv-reference",)
    assert not (install_root / "org.aperture.csv-reference").exists()
    assert registry.get("org.aperture.csv-reference").state is SourceState.REMOVED
    assert CanonicalEnrichmentService(database).get("accepted").status == "accepted"
