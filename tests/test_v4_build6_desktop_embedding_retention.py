from __future__ import annotations

from pathlib import Path

from natureai_next.application.enrichment_desktop import build_desktop_enrichment_controller
from natureai_next.application.enrichment_retention_ui import EnrichmentRetentionController
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.application.retention import RetentionProfileName
from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.synthesis_core import (
    FixtureSoundEventCapability,
    InProcessCapabilityRouter,
    InputKind,
)


def test_desktop_controller_activates_store_and_projects_sound(tmp_path: Path) -> None:
    database = tmp_path / "enrichment.sqlite3"
    controller = build_desktop_enrichment_controller(database)
    subject = SubjectRef(SubjectType.SOUND, "sound-desktop")
    assert controller.load(subject).items == ()


def test_retention_controller_previews_and_applies_without_deleting_accepted_by_default(
    tmp_path: Path,
) -> None:
    database = tmp_path / "enrichment.sqlite3"
    build_desktop_enrichment_controller(database)
    router = InProcessCapabilityRouter()
    router.register(FixtureSoundEventCapability())
    workspace = EnrichmentWorkspaceService(database, router, id_factory=lambda: "enr-retain")
    subject = SubjectRef(SubjectType.SOUND, "sound-retain")
    workspace.run(
        subject,
        capability_id="aperture.fixture.sound-events",
        input_kind=InputKind.SOUND,
        structured_input={"events": [{"start_seconds": 0, "end_seconds": 1, "label": "call"}]},
    )
    retention = EnrichmentRetentionController(database)
    preview = retention.preview(RetentionProfileName.MINIMAL)
    assert preview.destructive_accepted_delete is False
    assert preview.report.records_deleted == 1
    applied = retention.apply(preview)
    assert applied.records_deleted == 1
    assert workspace.project(subject, include_rejected=True).items == ()


def test_media_workspace_embeds_canonical_panel_by_selected_subject() -> None:
    source = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "CanonicalEnrichmentPanel" in source
    assert "currentRowChanged.connect(self._selection_changed)" in source
    assert "SubjectType(self._spec.asset_type)" in source
