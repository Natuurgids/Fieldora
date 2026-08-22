from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.capability_translation import CapabilityTranslationService
from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.enrichment_projection import EnrichmentProjectionService
from natureai_next.application.retention import (
    EnrichmentRetentionPolicy,
    EnrichmentSlimmingService,
    RetentionProfileName,
)
from natureai_next.domain.ai import ConfidenceBand, SuggestionCandidate
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core import (
    BioCLIPCapability,
    CapabilityRequest,
    FixtureSoundEventCapability,
    InputKind,
)
from natureai_next.ui.enrichment import default_renderer_registry


@dataclass
class FakeBioCLIPClassifier:
    identity: str = "fixture-tree-of-life"
    last_prediction_rows: tuple[dict[str, object], ...] = (
        {
            "scientific_name": "Erithacus rubecula",
            "common_name": "European robin",
            "rank": "species",
            "taxon_id": "2492466",
            "score": 0.91,
        },
    )
    released: bool = False

    def predict(self, image: Path, *, limit: int = 10):
        assert image.name == "robin.jpg"
        assert limit == 3
        return (
            SuggestionCandidate(
                taxon_public_id=None,
                label="Erithacus rubecula (European robin)",
                raw_score=0.91,
                calibrated_score=None,
                rank=1,
                confidence_band=ConfidenceBand.HIGH,
                taxonomic_level="species",
            ),
        )

    def release(self) -> None:
        self.released = True


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def test_bioclip_adapter_emits_producer_neutral_taxonomy_result(tmp_path: Path) -> None:
    classifier = FakeBioCLIPClassifier()
    engine = BioCLIPCapability(classifier)
    result = engine.execute(
        CapabilityRequest(
            engine.descriptor.capability_id,
            "photo-1",
            InputKind.PHOTO,
            tmp_path / "robin.jpg",
            parameters={"top_k": 3},
        )
    )
    candidate = result.candidates[0]
    assert candidate.shape.value == "taxonomy_candidate"
    assert candidate.value["scientific_name"] == "Erithacus rubecula"
    assert candidate.external_id == "treeoflife:2492466"
    assert candidate.confidence == 0.91
    engine.release()
    assert classifier.released is True


def test_sound_capability_translates_and_uses_timeline_renderer(tmp_path: Path) -> None:
    database = _database(tmp_path)
    engine = FixtureSoundEventCapability()
    result = engine.execute(
        CapabilityRequest(
            engine.descriptor.capability_id,
            "sound-1",
            InputKind.SOUND,
            structured_input={
                "events": [
                    {
                        "start_seconds": 1.25,
                        "end_seconds": 2.75,
                        "label": "bird call",
                        "confidence": 0.8,
                    }
                ]
            },
        )
    )
    CapabilityTranslationService(
        database, id_factory=lambda: "sound-event-1", clock_us=lambda: 100
    ).translate(SubjectRef(SubjectType.SOUND, "sound-1"), result)
    projected = (
        EnrichmentProjectionService(database)
        .for_subject(SubjectRef(SubjectType.SOUND, "sound-1"))
        .pending[0]
    )
    rendered = default_renderer_registry().render(projected)
    assert rendered.component == "timeline-event-list"
    assert rendered.title == "bird call"
    assert ("Start Seconds", "1.25") in rendered.fields
    assert rendered.can_accept is True


def test_standard_slimming_preserves_accepted_and_removes_diagnostics(tmp_path: Path) -> None:
    database = _database(tmp_path)
    translation = CapabilityTranslationService(
        database,
        id_factory=iter(("accepted", "rejected", "pending")).__next__,
        clock_us=lambda: 100,
    )
    engine = FixtureSoundEventCapability()
    result = engine.execute(
        CapabilityRequest(
            engine.descriptor.capability_id,
            "sound-1",
            InputKind.SOUND,
            structured_input={
                "events": [
                    {"start_seconds": 0, "end_seconds": 1, "label": "one"},
                    {"start_seconds": 1, "end_seconds": 2, "label": "two"},
                    {"start_seconds": 2, "end_seconds": 3, "label": "three"},
                ]
            },
        )
    )
    translation.translate(SubjectRef(SubjectType.SOUND, "sound-1"), result)
    store = CanonicalEnrichmentService(database)
    store.review("accepted", EnrichmentStatus.ACCEPTED, reviewer="observer", reviewed_at_us=200)
    store.review("rejected", EnrichmentStatus.REJECTED, reviewer="observer", reviewed_at_us=201)

    service = EnrichmentSlimmingService(database)
    preview = service.preview(EnrichmentRetentionPolicy.named(RetentionProfileName.STANDARD))
    assert preview.records_deleted == 1
    report = service.apply(EnrichmentRetentionPolicy.named(RetentionProfileName.STANDARD))
    assert report.records_deleted == 1

    remaining = EnrichmentProjectionService(database).for_subject(
        SubjectRef(SubjectType.SOUND, "sound-1"), include_rejected=True
    )
    assert {item.enrichment_id for item in remaining.items} == {"accepted", "pending"}
    accepted = store.get("accepted")
    assert accepted.status == "accepted"
    assert accepted.evidence == {}


def test_minimal_profile_does_not_delete_accepted_by_default(tmp_path: Path) -> None:
    database = _database(tmp_path)
    engine = FixtureSoundEventCapability()
    result = engine.execute(
        CapabilityRequest(
            engine.descriptor.capability_id,
            "sound-1",
            InputKind.SOUND,
            structured_input={"events": [{"start_seconds": 0, "end_seconds": 1}]},
        )
    )
    CapabilityTranslationService(
        database, id_factory=lambda: "accepted", clock_us=lambda: 100
    ).translate(SubjectRef(SubjectType.SOUND, "sound-1"), result)
    CanonicalEnrichmentService(database).review(
        "accepted", EnrichmentStatus.ACCEPTED, reviewer="observer"
    )
    report = EnrichmentSlimmingService(database).apply(
        EnrichmentRetentionPolicy.named(RetentionProfileName.MINIMAL)
    )
    assert report.accepted_records_deleted == 0
    assert CanonicalEnrichmentService(database).get("accepted").status == "accepted"
