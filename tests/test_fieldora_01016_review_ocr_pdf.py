import json
import sqlite3
from pathlib import Path

from natureai_next.application.enrichment import (
    CanonicalEnrichment,
    CanonicalEnrichmentService,
)
from natureai_next.infrastructure.database.ai_review import SqliteSuggestionStore
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


def test_assigned_canonical_review_is_audited_and_cleared_on_completion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(database),), "0.11.3").activate(
        "enrichment"
    )
    service = CanonicalEnrichmentService(database)
    service.store(
        CanonicalEnrichment(
            "enrichment-1",
            "document",
            "document-1",
            "document.ocr",
            "fieldora.document-ocr",
            status="pending_review",
            payload={"text": "Field note"},
        )
    )
    service.assign_review(
        "enrichment-1",
        assigned_to="reviewer-1",
        assigned_by="administrator-1",
        note="Check the locality",
        assigned_at_us=10,
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT assigned_to FROM enrichment_review_assignments"
        ).fetchone() == ("reviewer-1",)
    from natureai_next.domain.enrichment import EnrichmentStatus

    service.review(
        "enrichment-1",
        EnrichmentStatus.ACCEPTED,
        reviewer="reviewer-1",
        reviewed_at_us=20,
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM enrichment_review_assignments"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT action FROM enrichment_review_assignment_events ORDER BY id"
        ).fetchall() == [("assigned",), ("completed",)]


def test_photo_review_assignment_filters_the_queue(tmp_path: Path) -> None:
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.11.3").apply(connection)
        connection.execute(
            "INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us)"
            " VALUES('asset-1','image','active',1,1)"
        )
        connection.execute(
            "INSERT INTO model_packages(public_id,model_identity,semantic_version,model_family,"
            "artifact_checksum,manifest_json,license_json,install_path_token,installation_state,active)"
            " VALUES('package-1','test','1','test','sum','{}','{}','model','installed',1)"
        )
        connection.execute(
            "INSERT INTO model_variants(public_id,package_id,variant_identity,runtime,precision,"
            "device_requirements_json,preprocessing_identity,active)"
            " VALUES('variant-1',1,'default','torch','fp32','{}','prep',1)"
        )
        connection.execute(
            "INSERT INTO inference_runs(public_id,model_variant_id,execution_provider,parameter_json,"
            "application_version,started_at_us)"
            " VALUES('run-1',1,'cpu','{}','0.11.3',1)"
        )
        connection.execute(
            "INSERT INTO ai_suggestions(public_id,asset_id,inference_run_id,suggestion_type,"
            "candidate_label,raw_score,rank,provenance_json,review_state,created_at_us)"
            " VALUES('suggestion-1',1,1,'taxonomy','Species',0.9,1,'{}','pending',1)"
        )
        connection.commit()
    store = SqliteSuggestionStore(factory)
    store.assign_review(
        suggestion_public_id="suggestion-1",
        assigned_to="reviewer-1",
        assigned_by="administrator-1",
        now_us=10,
        note="Specialist review",
    )
    assert store.page(state="pending", assigned_to="reviewer-1").items[0].assigned_to == "reviewer-1"
    assert store.page(state="pending", assigned_to="").items == ()


def test_ocr_catalog_and_pdf_ui_contracts_are_packaged() -> None:
    root = Path(__file__).parents[1]
    models = json.loads(
        (root / "src/natureai_next/resources/models.json").read_text(encoding="utf-8")
    )
    ocr = next(item for item in models["models"] if item["key"] == "document-ocr-v1")
    assert ocr["input"]["asset_types"] == ["document"]
    assert ocr["factory"].endswith(":DocumentOCRCapability")
    media = (root / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "QPdfView.PageMode.MultiPage" in media
    assert "QPdfView.ZoomMode.FitToWidth" in media
    assert "def set_page_rail" in media


def test_disabled_libraries_hide_their_ai_review_tabs() -> None:
    root = Path(__file__).parents[1]
    knowledge = (root / "src/natureai_next/ui/qt/knowledge_base.py").read_text(
        encoding="utf-8"
    )
    application = (root / "src/natureai_next/ui/qt/application.py").read_text(
        encoding="utf-8"
    )
    assert "setTabVisible(index, bool(enabled))" in knowledge
    assert "set_library_capability_enabled(" in application
