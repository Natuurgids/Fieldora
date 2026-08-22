from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.capability_translation import CapabilityTranslationService
from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.enrichment_projection import EnrichmentProjectionService
from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceRemovalOptions,
    SourceState,
)
from natureai_next.domain.enrichment import (
    CanonicalCandidate,
    CanonicalShape,
    EnrichmentStatus,
    SubjectRef,
    SubjectType,
)
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core import (
    CapabilityDescriptor,
    CapabilityRequest,
    CapabilityResult,
    InProcessCapabilityRouter,
    InputKind,
)


@dataclass
class FixturePhotoCapability:
    descriptor = CapabilityDescriptor(
        capability_id="org.aperture.test.photo-label",
        display_name="Test Photo Label",
        version="1.0.0",
        inputs=frozenset({InputKind.PHOTO}),
        outputs=frozenset({CanonicalShape.LABEL.value}),
    )
    released: bool = False

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        assert request.input_kind is InputKind.PHOTO
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            run_id="run-1",
            source_name="Bundled test labels",
            source_version="2026.1",
            source_checksum="abc123",
            attribution="Aperture test fixture",
            licence="CC0-1.0",
            candidates=(
                CanonicalCandidate(
                    CanonicalShape.LABEL,
                    {"label": "European robin"},
                    confidence=0.93,
                ),
            ),
        )

    def release(self) -> None:
        self.released = True


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "enrichment.sqlite3"
    registry = SubsystemDatabaseRegistry((enrichment_descriptor(database_path),), "4.0.0.dev1")
    registry.activate("enrichment")
    return database_path


def test_capability_to_pending_review_to_observation_projection(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    source_id = "org.aperture.test.photo-label"
    sources = SourceRegistryService(database_path)
    sources.register(
        SourceRecord(
            source_id=source_id,
            kind="capability",
            display_name="Test Photo Label",
            version="1.0.0",
            state=SourceState.INSTALLED,
            licence="CC0-1.0",
        )
    )

    engine = FixturePhotoCapability()
    router = InProcessCapabilityRouter()
    router.register(engine)
    subject = SubjectRef(SubjectType.PHOTO, "photo-1")
    result = router.execute(
        CapabilityRequest(source_id, subject.public_id, InputKind.PHOTO, tmp_path / "photo.jpg")
    )
    ids = iter(("enrichment-1",))
    translation = CapabilityTranslationService(
        database_path, id_factory=lambda: next(ids), clock_us=lambda: 100
    )
    outcome = translation.translate(subject, result)

    projection = EnrichmentProjectionService(database_path)
    pending = projection.for_subject(subject)
    assert outcome.enrichment_ids == ("enrichment-1",)
    assert pending.pending[0].value == {"label": "European robin"}
    assert pending.pending[0].provenance["producer_version"] == "1.0.0"

    store = CanonicalEnrichmentService(database_path)
    store.review(
        "enrichment-1",
        EnrichmentStatus.ACCEPTED,
        reviewer="observer",
        reviewed_at_us=200,
    )
    observation = projection.for_observation("observation-1", (subject,))
    assert observation.accepted[0].summary == "European robin"

    router.deactivate(source_id)
    sources.remove(source_id, SourceRemovalOptions())
    assert engine.released is True
    assert sources.get(source_id).state is SourceState.REMOVED
    assert projection.for_subject(subject).accepted[0].provenance["licence"] == "CC0-1.0"


def test_source_removal_can_delete_pending_without_accepted(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    sources = SourceRegistryService(database_path)
    source_id = "org.aperture.test.photo-label"
    sources.register(SourceRecord(source_id, "capability", "Test", "1", SourceState.INSTALLED))
    translation_ids = iter(("pending", "accepted"))
    translation = CapabilityTranslationService(
        database_path, id_factory=lambda: next(translation_ids), clock_us=lambda: 100
    )
    subject = SubjectRef(SubjectType.PHOTO, "photo-1")
    result = CapabilityResult(
        source_id,
        "Test",
        "1",
        (
            CanonicalCandidate(CanonicalShape.LABEL, {"label": "one"}),
            CanonicalCandidate(CanonicalShape.LABEL, {"label": "two"}),
        ),
    )
    translation.translate(subject, result)
    store = CanonicalEnrichmentService(database_path)
    store.review("accepted", EnrichmentStatus.ACCEPTED, reviewer="observer")

    sources.remove(
        source_id,
        SourceRemovalOptions(delete_pending_results=True, delete_rejected_results=True),
    )
    remaining = EnrichmentProjectionService(database_path).for_subject(subject)
    assert [item.enrichment_id for item in remaining.items] == ["accepted"]
