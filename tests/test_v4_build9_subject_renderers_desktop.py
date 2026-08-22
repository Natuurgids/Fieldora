from pathlib import Path

from natureai_next.application.enrichment_projection import ProjectedEnrichment
from natureai_next.domain.enrichment import CanonicalShape
from natureai_next.ui.enrichment.renderers import default_renderer_registry


def projected(shape: CanonicalShape, *, value=None, target=None):
    return ProjectedEnrichment(
        enrichment_id="enr-1",
        shape=shape.value,
        status="pending_review",
        summary="candidate",
        value=value or {"label": "candidate"},
        target=target or {},
        confidence=0.8,
        provenance={"producer_name": "fixture", "producer_version": "1"},
    )


def test_spatial_and_timeline_renderers_expose_normalized_visualization_data():
    registry = default_renderer_registry()
    spatial = registry.render(
        projected(
            CanonicalShape.BOUNDING_BOX,
            target={"left": -0.2, "top": 0.1, "right": 1.3, "bottom": 0.7},
        )
    )
    assert spatial.component == "spatial-overlay"
    assert spatial.visualization["boxes"][0] == {"x": 0.0, "y": 0.1, "width": 1.0, "height": 0.6}

    timeline = registry.render(
        projected(
            CanonicalShape.TIME_FREQUENCY_REGION,
            target={"start_seconds": 1.25, "end_seconds": 2.75, "low_hz": 800, "high_hz": 4200},
        )
    )
    assert timeline.visualization["kind"] == "time-frequency"
    assert timeline.visualization["start_seconds"] == 1.25
    assert timeline.visualization["high_hz"] == 4200.0


def test_transcript_and_document_renderers_keep_readable_subject_context():
    registry = default_renderer_registry()
    transcript = registry.render(
        projected(
            CanonicalShape.TRANSCRIPT_SEGMENT,
            value={"text": "Aperture offline transcript", "speaker": "observer"},
            target={"start_seconds": 3, "end_seconds": 5},
        )
    )
    assert transcript.visualization["text"] == "Aperture offline transcript"
    assert transcript.visualization["speaker"] == "observer"

    document = registry.render(
        projected(
            CanonicalShape.DOCUMENT_REGION,
            value={"text": "Table heading", "region_type": "heading"},
            target={"page": 4, "x": 0.1, "y": 0.2, "width": 0.6, "height": 0.1},
        )
    )
    assert document.visualization["page"] == 4
    assert document.visualization["box"]["width"] == 0.6


def test_desktop_source_wires_canonical_controller_into_primary_subject_workspaces():
    root = Path(__file__).resolve().parents[1]
    application = (root / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    library = (root / "src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    observations = (root / "src/natureai_next/ui/qt/observations.py").read_text(encoding="utf-8")

    assert "build_desktop_enrichment_controller" in application
    assert "enrichment_controller=self._enrichment_controller" in application
    assert "SubjectType.PHOTO" in library
    assert "CanonicalEnrichmentPanel" in library
    assert "SubjectType.OBSERVATION" in observations
    assert "Accepted observation evidence" in observations
