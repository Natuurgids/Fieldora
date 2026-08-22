from __future__ import annotations

from pathlib import Path

from natureai_next.application.enrichment_ui import EnrichmentWorkspaceController
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceState,
)
from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core import (
    FixtureSoundEventCapability,
    InProcessCapabilityRouter,
    InputKind,
)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def test_headless_enrichment_controller_renders_and_reviews_canonical_records(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    router = InProcessCapabilityRouter()
    router.register(FixtureSoundEventCapability())
    workspace = EnrichmentWorkspaceService(
        database, router, id_factory=lambda: "enr-1", clock_us=lambda: 100
    )
    subject = SubjectRef(SubjectType.SOUND, "sound-1")
    workspace.run(
        subject,
        capability_id="aperture.fixture.sound-events",
        input_kind=InputKind.SOUND,
        structured_input={"events": [{"start_seconds": 2, "end_seconds": 4, "label": "bird call"}]},
    )

    controller = EnrichmentWorkspaceController(workspace, reviewer_provider=lambda: "observer")
    pending = controller.load(subject)
    assert pending.pending_count == 1
    assert pending.items[0].component == "timeline-event-list"
    assert pending.items[0].can_accept is True

    accepted = controller.accept(subject, "enr-1")
    assert accepted.accepted_count == 1
    assert accepted.pending_count == 0
    assert accepted.items[0].can_accept is False


def test_source_registry_lists_sources_and_enrichment_counts(tmp_path: Path) -> None:
    database = _database(tmp_path)
    registry = SourceRegistryService(database)
    registry.register(SourceRecord("source.b", "source", "Beta", "2", SourceState.OFFLINE))
    registry.register(SourceRecord("source.a", "capability", "Alpha", "1", SourceState.INSTALLED))

    records = registry.list()
    assert [record.source_id for record in records] == ["source.a", "source.b"]
    assert registry.enrichment_counts("source.a") == {}
