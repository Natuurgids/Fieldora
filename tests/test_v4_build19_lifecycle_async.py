import time
from pathlib import Path

import pytest

from natureai_next.application.capability_execution import CapabilityRunState
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceState,
)
from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core.contracts import InputKind
from natureai_next.synthesis_core.runtime import InProcessCapabilityRouter
from natureai_next.synthesis_core.test_sound import FixtureSoundEventCapability


def activate(tmp_path: Path) -> Path:
    db = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(db),), "4.0.0.dev1").activate("enrichment")
    return db


def test_source_installation_can_be_verified_missing_relinked_and_audited(tmp_path: Path):
    db = activate(tmp_path)
    service = SourceRegistryService(db)
    service.register(SourceRecord("source.one", "source", "One", "1", SourceState.INSTALLED))
    missing = tmp_path / "missing.bundle"
    service.attach_installation("source.one", runtime_path=missing)
    assert service.verify_installation("source.one") is SourceState.MISSING
    assert service.get("source.one").state is SourceState.MISSING
    missing.write_text("ok", encoding="utf-8")
    assert service.recover("source.one") is SourceState.INSTALLED
    events = service.lifecycle_events("source.one")
    assert [event["action"] for event in events][-2:] == ["verify", "verify"]
    assert events[-1]["to_state"] == "installed"


def test_source_superseding_preserves_old_identity_and_links_replacement(tmp_path: Path):
    db = activate(tmp_path)
    service = SourceRegistryService(db)
    service.register(SourceRecord("source.v1", "source", "Dataset", "1", SourceState.INSTALLED))
    service.supersede(
        "source.v1",
        SourceRecord("source.v2", "source", "Dataset", "2", SourceState.INSTALLED),
    )
    assert service.get("source.v1").state is SourceState.SUPERSEDED
    assert service.get("source.v2").state is SourceState.INSTALLED
    assert service.installation("source.v1").replacement_source_id == "source.v2"


def test_async_capability_execution_reports_progress_and_creates_records(tmp_path: Path):
    db = activate(tmp_path)
    router = InProcessCapabilityRouter()
    router.register(FixtureSoundEventCapability())
    workspace = EnrichmentWorkspaceService(db, router, id_factory=lambda: "enr-async")
    run = workspace.run_async(
        SubjectRef(SubjectType.SOUND, "sound-async"),
        capability_id="aperture.fixture.sound-events",
        input_kind=InputKind.SOUND,
        structured_input={"events": [{"start_seconds": 0.5, "end_seconds": 1.0, "label": "call"}]},
        parameters={"default_label": "event"},
    )
    outcome = run.result(timeout=5)
    assert outcome.created_enrichment_ids == ("enr-async",)
    assert run.progress.state is CapabilityRunState.SUCCEEDED
    assert run.progress.current == 3
    workspace.shutdown()


def test_async_run_can_be_cancelled_before_operation_finishes(tmp_path: Path):
    from natureai_next.application.capability_execution import CapabilityExecutionPool

    pool = CapabilityExecutionPool(max_workers=1)

    def slow(cancel, progress):
        for index in range(100):
            time.sleep(0.002)
            progress(index, 100, "working")
        return 1

    run = pool.submit(slow)
    run.cancel()
    with pytest.raises((InterruptedError, Exception)):
        run.result(timeout=5)
    assert run.progress.state in {CapabilityRunState.CANCELLED, CapabilityRunState.CANCELLING}
    pool.shutdown()


def test_media_workspace_uses_async_progress_and_cancellation_contract():
    text = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "run_capability_batch_async(" in text
    assert "CapabilityBatchProgressDialog" in text
    assert "cancel_for_disabled_workspace" in text
