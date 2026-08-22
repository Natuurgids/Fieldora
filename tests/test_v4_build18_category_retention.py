from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from natureai_next.application.retention import (
    EnrichmentRetentionPolicy,
    EnrichmentSlimmingService,
    RetentionProfileName,
)
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def _insert(database: Path) -> None:
    payload = {
        "text": "Recognised invoice text",
        "geographic_assertion": {"latitude": 50.1, "longitude": 4.2},
        "probabilities": [0.1, 0.9],
        "diagnostics": {"duration_ms": 24},
        "spectrogram_path": "/cache/a.png",
        "ocr_intermediate": "/tmp/deskew.png",
        "source_package_path": "/sources/map.zip",
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO enrichment_records(
                enrichment_id,subject_type,subject_public_id,enrichment_type,schema_version,
                producer_id,status,payload_json,evidence_json,source_snapshot_json,
                created_at_us,updated_at_us
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "accepted-1",
                "document",
                "doc-1",
                "document_region",
                1,
                "fixture",
                "accepted",
                json.dumps(payload),
                json.dumps({"raw_output": "verbose", "thumbnail_path": "/cache/t.png"}),
                "{}",
                1,
                1,
            ),
        )


def test_minimal_category_retention_preserves_ocr_text_and_geography(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    service = EnrichmentSlimmingService(database)
    preview = service.preview(EnrichmentRetentionPolicy.named(RetentionProfileName.MINIMAL))
    assert preview.accepted_records_deleted == 0
    assert preview.accepted_records_preserved == 1
    assert preview.probability_vectors_removed == 1
    assert preview.diagnostics_removed == 2
    assert preview.media_cache_references_removed == 2
    assert preview.ocr_intermediates_removed == 1
    assert preview.source_package_references_removed == 1
    assert preview.reproducibility_impacted_records == 1

    report = service.apply(EnrichmentRetentionPolicy.named(RetentionProfileName.MINIMAL))
    assert report == preview
    with sqlite3.connect(database) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM enrichment_records WHERE enrichment_id='accepted-1'"
            ).fetchone()[0]
        )
        assert payload["text"] == "Recognised invoice text"
        assert payload["geographic_assertion"] == {"latitude": 50.1, "longitude": 4.2}
        assert "probabilities" not in payload
        assert "ocr_intermediate" not in payload
        audit = connection.execute(
            "SELECT profile,report_json FROM enrichment_retention_audit ORDER BY audit_id DESC LIMIT 1"
        ).fetchone()
        assert audit[0] == "minimal"
        assert json.loads(audit[1])["accepted_records_preserved"] == 1


def test_research_profile_keeps_reproducibility_material(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    report = EnrichmentSlimmingService(database).preview(
        EnrichmentRetentionPolicy.named(RetentionProfileName.RESEARCH)
    )
    assert report.records_deleted == 0
    assert report.probability_vectors_removed == 0
    assert report.media_cache_references_removed == 0
    assert report.ocr_intermediates_removed == 0
    assert report.source_package_references_removed == 0
    assert report.reproducibility_impacted_records == 0
